import socket
import sys
import threading
import time

import election
from utils import (
    MSG_ELECTION, MSG_COORDINATOR, MSG_PING, MSG_PONG,
    MSG_STATUS, MSG_INICIAR_ELEICAO,
    enviar_mensagem, receber_mensagem, codificar, agora,
)


class Node:
    def __init__(self, id, host, porta, rede, passo_delay=0.6, imprimir=False):
        self.id = id
        self.host = host
        self.porta = porta
        self.sucessor = None
        self.rede = rede

        self.eh_lider = False
        self.lider_conhecido = None
        self.ativo = False

        self.passo_delay = passo_delay
        self.imprimir = imprimir

        self._socket_servidor = None
        self._thread_servidor = None
        self._thread_monitor = None

    def iniciar(self):
        if self.ativo:
            return

        servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if sys.platform != "win32":
            servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            servidor.bind((self.host, self.porta))
            servidor.listen()
        except OSError as erro:
            servidor.close()
            self.log(f"❌ Nó {self.id} não conseguiu escutar na porta "
                     f"{self.porta}: {erro}", tipo="falha")
            return

        # Bind feito antes de subir as threads: falhas são percebidas imediatamente
        # e derrubar() sempre encontra um socket real para fechar.
        self._socket_servidor = servidor
        self.ativo = True
        self._thread_servidor = threading.Thread(target=self._loop_servidor, daemon=True)
        self._thread_servidor.start()
        self._thread_monitor = threading.Thread(target=self._loop_monitor, daemon=True)
        self._thread_monitor.start()
        self.sucessor, _ = self.rede.proximo_vivo(self.id)
        self.log(f"🟢 Nó {self.id} entrou no anel (escutando na porta {self.porta}).",
                 tipo="sistema")

    def derrubar(self):
        if not self.ativo:
            return
        era_lider = self.eh_lider
        self.ativo = False
        self.eh_lider = False
        # Zera estado para forçar redescoberta ao reviver: um nó revivido
        # não pode confiar nos valores antigos de líder e sucessor.
        self.lider_conhecido = None
        self.sucessor = None
        try:
            if self._socket_servidor is not None:
                self._socket_servidor.close()
        except OSError:
            pass
        self._socket_servidor = None
        self.log(f"🔴 Nó {self.id} CAIU" + (" (era o líder!)" if era_lider else "") + ".",
                 tipo="falha")

    def reviver(self):
        self.iniciar()

    def _loop_servidor(self):
        # Referência local à thread: se o nó cair e reviver, a nova thread tem
        # outra identidade — esta percebe e se encerra sem precisar de flag extra.
        minha_thread = threading.current_thread()
        meu_socket = self._socket_servidor
        while self.ativo and self._thread_servidor is minha_thread:
            try:
                conexao, _ = meu_socket.accept()
            except OSError:
                break
            threading.Thread(target=self._tratar_conexao, args=(conexao,),
                             daemon=True).start()

    def _tratar_conexao(self, conexao):
        with conexao:
            conexao.settimeout(2.0)
            mensagem = receber_mensagem(conexao)
            if mensagem is None:
                return
            tipo = mensagem.get("tipo")

            try:
                if tipo == MSG_PING:
                    conexao.sendall(codificar({"tipo": MSG_PONG, "id": self.id}))
                    return
                if tipo == MSG_STATUS:
                    conexao.sendall(codificar(self.snapshot()))
                    return
            except OSError:
                return

        if tipo == MSG_INICIAR_ELEICAO:
            self.rede.eleicao_em_andamento = True
            election.iniciar_eleicao(self)
        elif tipo == MSG_ELECTION:
            election.processar_eleicao(self, mensagem)
        elif tipo == MSG_COORDINATOR:
            election.processar_coordenador(self, mensagem)

    def _loop_monitor(self):
        # Atraso inicial escalonado por id: evita que vários nós disparem
        # eleições simultâneas quando sobem ao mesmo tempo.
        time.sleep(1.0 + 0.15 * self.id)

        minha_thread = threading.current_thread()
        while self.ativo and self._thread_monitor is minha_thread:
            time.sleep(1.5)
            if not self.ativo or self._thread_monitor is not minha_thread:
                break

            sucessor = self.sucessor
            if sucessor is None or sucessor["id"] == self.id:
                self.sucessor, _ = self.rede.proximo_vivo(self.id)
                continue

            resposta = enviar_mensagem(sucessor["host"], sucessor["porta"],
                                       {"tipo": MSG_PING}, esperar_resposta=True)
            if resposta is not None:
                ideal, _ = self.rede.proximo_vivo(self.id)
                if ideal is not None and ideal["id"] != sucessor["id"]:
                    self.sucessor = ideal
                continue

            morto = sucessor["id"]
            novo_sucessor, pulados = self.rede.proximo_vivo(self.id, ignorar={morto})
            self.sucessor = novo_sucessor

            lider_caiu = (self.lider_conhecido is not None
                          and (self.lider_conhecido == morto
                               or self.lider_conhecido in pulados))

            if not lider_caiu:
                self.log(f"🔧 Nó {self.id} percebeu que seu sucessor (nó {morto}) caiu; "
                         f"anel reconfigurado (novo sucessor: "
                         f"{novo_sucessor['id'] if novo_sucessor else 'nenhum'}).",
                         tipo="falha")
                continue

            self.log(f"⚠️  Nó {self.id} detectou que o líder (nó {self.lider_conhecido}) caiu!",
                     tipo="falha")
            self.lider_conhecido = None
            with self.rede.lock:
                ja_em_curso = self.rede.eleicao_em_andamento
                if not ja_em_curso:
                    self.rede.eleicao_em_andamento = True
            if not ja_em_curso:
                election.iniciar_eleicao(self)

    def marcar_transito(self, de_id, para_id, mensagem):
        # Dicionário por remetente (não slot único): permite múltiplas mensagens
        # simultâneas sem que uma apague o rastro da outra na animação.
        with self.rede.lock:
            self.rede.transitos[self.id] = {
                "de": de_id,
                "para": para_id,
                "tipo": mensagem.get("tipo"),
                "ids": list(mensagem.get("ids", [])),
                "lider": mensagem.get("lider"),
                "inicio": time.time(),
            }

    def limpar_transito(self):
        with self.rede.lock:
            self.rede.transitos.pop(self.id, None)

    def log(self, texto, tipo="info"):
        linha = {"hora": agora(), "no": self.id, "tipo": tipo, "texto": texto}
        with self.rede.lock:
            self.rede.logs.append(linha)
        if self.imprimir:
            print(f"[{linha['hora']}] (nó {self.id}) {texto}")

    def snapshot(self):
        return {
            "id": self.id,
            "porta": self.porta,
            "ativo": self.ativo,
            "eh_lider": self.eh_lider,
            "lider_conhecido": self.lider_conhecido,
            "sucessor": self.sucessor["id"] if self.sucessor else None,
        }


class Rede:
    def __init__(self, ids, host="127.0.0.1", porta_base=5001, passo_delay=0.6):
        self.host = host
        self.lock = threading.Lock()
        self.logs = []
        self.transitos = {}
        self.eleicao_em_andamento = False

        self.anel = [
            {"id": id, "host": host, "porta": porta_base + i}
            for i, id in enumerate(ids)
        ]

        self.nos = {
            n["id"]: Node(n["id"], host, n["porta"], self, passo_delay=passo_delay)
            for n in self.anel
        }

    def proximo_vivo(self, id_atual, ignorar=()):
        total = len(self.anel)
        idx = next((i for i, n in enumerate(self.anel) if n["id"] == id_atual), None)
        if idx is None:
            return None, []

        pulados = []
        for salto in range(1, total):
            candidato = self.anel[(idx + salto) % total]
            cid = candidato["id"]
            if cid == id_atual:
                break
            no = self.nos[cid]
            if no.ativo and cid not in ignorar:
                return candidato, pulados
            pulados.append(cid)
        return None, pulados

    def maior_vivo(self, ids):
        vivos = [i for i in ids if i in self.nos and self.nos[i].ativo]
        return max(vivos) if vivos else None

    def _reconfigurar_sucessores(self):
        # NÃO chamado em derrubar(): o antecessor precisa manter o ponteiro
        # antigo para detectar a queda via PING.
        for n in self.anel:
            no = self.nos[n["id"]]
            if no.ativo:
                no.sucessor, _ = self.proximo_vivo(no.id)

    def iniciar_todos(self):
        for no in self.nos.values():
            no.iniciar()
        self._reconfigurar_sucessores()

    def parar_todos(self):
        for no in self.nos.values():
            no.derrubar()

    def derrubar(self, id_no):
        self.nos[id_no].derrubar()

    def reviver(self, id_no):
        self.nos[id_no].reviver()
        no = self.nos[id_no]
        if no.ativo:
            self._reconfigurar_sucessores()
            self.iniciar_eleicao_em(id_no)

    def iniciar_eleicao_em(self, id_no):
        self.eleicao_em_andamento = True
        threading.Thread(target=election.iniciar_eleicao,
                         args=(self.nos[id_no],), daemon=True).start()

    def estados(self):
        return [self.nos[n["id"]].snapshot() for n in self.anel]

    def lider_atual(self):
        for n in self.anel:
            no = self.nos[n["id"]]
            if no.ativo and no.eh_lider:
                return no.id
        return None
