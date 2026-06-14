"""
node.py
=======
Define o NÓ (processo participante do anel) e a REDE (que cria e gerencia
vários nós de uma vez). É aqui que a parte de "sockets/threads" mora.

Cada NÓ é, ao mesmo tempo:
  - um SERVIDOR: tem um socket que fica ESCUTANDO mensagens que chegam;
  - um CLIENTE: ABRE conexões para enviar mensagens ao seu sucessor no anel.

Cada NÓ roda em DUAS threads de fundo:
  - thread do servidor    -> aceita conexões e trata cada mensagem que chega;
  - thread do monitor     -> de tempos em tempos verifica se o líder está vivo
                             (detecção de falha) e, se não estiver, inicia uma
                             nova eleição automaticamente.

A classe REDE existe só para facilitar: ela cria N nós em portas sequenciais,
guarda um log compartilhado (linha do tempo única) e o "estado de trânsito"
(qual mensagem está viajando agora) para a animação no Streamlit.
"""

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
    """Um processo participante do anel de eleição."""

    def __init__(self, id, host, porta, anel, rede, passo_delay=0.6, imprimir=False):
        # --- Identidade e topologia ---
        self.id = id                  # identificador único (inteiro). MAIOR id vence.
        self.host = host              # endereço (localhost na demo)
        self.porta = porta            # porta TCP onde este nó escuta
        self.anel = anel              # lista [{id, host, porta}, ...] em ordem de anel
        self.rede = rede              # referência à Rede (log e trânsito compartilhados)

        # --- Estado do algoritmo ---
        self.eh_lider = False             # este nó é o líder atual?
        self.lider_conhecido = None       # qual nó este nó acredita ser o líder
        self.ativo = False                # o nó está "vivo" (servidor escutando)?

        # --- Configuração da demonstração ---
        self.passo_delay = passo_delay    # atraso por salto (deixa a animação visível)
        self.imprimir = imprimir          # se True, também imprime logs no terminal

        # --- Objetos internos de rede/threads ---
        self._socket_servidor = None
        self._thread_servidor = None
        self._thread_monitor = None

    # ------------------------------------------------------------------ #
    # CICLO DE VIDA DO NÓ: iniciar / derrubar (falha) / reviver           #
    # ------------------------------------------------------------------ #

    def iniciar(self):
        """Liga o nó: começa a escutar (servidor) e a monitorar o líder.

        IMPORTANTE: o socket é criado e BINDADO aqui (na thread que chamou
        iniciar), ANTES de subir as threads de fundo. Antes ele era criado lá
        dentro do _loop_servidor, o que causava dois bugs:
          1. se o bind falhasse (porta ocupada), a exceção morria em silêncio
             dentro da thread daemon — o nó "parecia" vivo (ativo=True), mas não
             escutava nada, e o anel quebrava sem aviso;
          2. uma corrida entre iniciar()/derrubar() podia deixar um socket
             bindado e nunca fechado (vazamento de porta -> WinError 10048).
        Criando e bindando aqui, falhas são percebidas NA HORA e derrubar()
        sempre encontra um socket real para fechar.
        """
        if self.ativo:
            return

        servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Em Unix, SO_REUSEADDR libera a porta logo após o close (evita TIME_WAIT
        # ao religar o mesmo nó). No Windows NÃO usamos SO_REUSEADDR (lá ele
        # permitiria DOUBLE-BIND na mesma porta); o reset seguro no Windows é
        # garantido pela interface, que usa uma FAIXA DE PORTAS NOVA a cada anel.
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

        self._socket_servidor = servidor
        self.ativo = True
        self._thread_servidor = threading.Thread(target=self._loop_servidor, daemon=True)
        self._thread_servidor.start()
        self._thread_monitor = threading.Thread(target=self._loop_monitor, daemon=True)
        self._thread_monitor.start()
        self.log(f"🟢 Nó {self.id} entrou no anel (escutando na porta {self.porta}).",
                 tipo="sistema")

    def derrubar(self):
        """
        Simula a FALHA do nó: fecha o socket do servidor.

        Depois disso, qualquer tentativa de conexão a este nó vai falhar
        (ConnectionRefused) — é exatamente assim que os outros nós percebem
        que ele caiu.
        """
        if not self.ativo:
            return
        era_lider = self.eh_lider
        self.ativo = False
        self.eh_lider = False
        # Esquece também quem ERA o líder: um nó que cai e volta não pode
        # confiar no estado antigo. Sem isso, um ex-líder revivido continuava
        # com lider_conhecido == self.id e o monitor o ignorava para sempre.
        self.lider_conhecido = None
        try:
            if self._socket_servidor is not None:
                self._socket_servidor.close()  # para de escutar -> fica inacessível
        except OSError:
            pass
        self._socket_servidor = None
        self.log(f"🔴 Nó {self.id} CAIU" + (" (era o líder!)" if era_lider else "") + ".",
                 tipo="falha")

    def reviver(self):
        """Liga novamente um nó que havia caído (reentra no anel)."""
        self.iniciar()

    # ------------------------------------------------------------------ #
    # LADO SERVIDOR: escutar e tratar mensagens que chegam                #
    # ------------------------------------------------------------------ #

    def _loop_servidor(self):
        """Aceita conexões enquanto o nó estiver vivo.

        O socket de escuta já foi criado e bindado em iniciar(); aqui só fica o
        laço de accept(). Quando derrubar() fecha o socket, o accept() levanta
        OSError e encerramos o laço de forma limpa.

        Guardamos referências LOCAIS à thread e ao socket: se o nó for derrubado
        e revivido muito rápido, iniciar() cria uma thread/socket NOVOS — a
        thread antiga percebe que foi substituída e se encerra, em vez de ficar
        duas threads aceitando conexões ao mesmo tempo.
        """
        minha_thread = threading.current_thread()
        meu_socket = self._socket_servidor
        while self.ativo and self._thread_servidor is minha_thread:
            try:
                conexao, _ = meu_socket.accept()
            except OSError:
                break  # socket foi fechado em derrubar(): encerramos o loop.
            # Tratamos cada conexão em sua própria thread para não travar a fila.
            threading.Thread(target=self._tratar_conexao, args=(conexao,),
                             daemon=True).start()

    def _tratar_conexao(self, conexao):
        """Lê UMA mensagem da conexão e decide o que fazer com base no 'tipo'."""
        # PING e STATUS RESPONDEM nesta mesma conexão (precisam dela aberta).
        with conexao:
            # Timeout de leitura: se alguém conectar e não enviar nada, esta
            # thread não fica presa para sempre esperando bytes que não vêm.
            conexao.settimeout(2.0)
            mensagem = receber_mensagem(conexao)
            if mensagem is None:
                return
            tipo = mensagem.get("tipo")

            try:
                if tipo == MSG_PING:
                    # Alguém está checando se estou vivo: respondo PONG.
                    conexao.sendall(codificar({"tipo": MSG_PONG, "id": self.id}))
                    return

                if tipo == MSG_STATUS:
                    # O client.py perguntou meu estado: devolvo um resumo.
                    conexao.sendall(codificar(self.snapshot()))
                    return
            except OSError:
                return  # quem perguntou desistiu e fechou a conexão: tudo bem.

        # ELEICAO/COORDENADOR não respondem por esta conexão: o encaminhamento
        # abre uma conexão NOVA para o sucessor. Por isso liberamos o socket de
        # entrada ANTES de encaminhar (que é lento: tem passo_delay). Assim não
        # seguramos a conexão do antecessor durante toda a propagação.
        if tipo == MSG_INICIAR_ELEICAO:
            # Um cliente externo pediu para EU começar uma eleição.
            self.rede.eleicao_em_andamento = True
            election.iniciar_eleicao(self)

        elif tipo == MSG_ELECTION:
            # Mensagem de eleição circulando: aplico a lógica do algoritmo.
            election.processar_eleicao(self, mensagem)

        elif tipo == MSG_COORDINATOR:
            # Anúncio do novo líder circulando.
            election.processar_coordenador(self, mensagem)

    # ------------------------------------------------------------------ #
    # DETECÇÃO DE FALHA: o monitor que vigia o líder                      #
    # ------------------------------------------------------------------ #

    def _loop_monitor(self):
        """
        De tempos em tempos, verifica se o líder ainda responde.

        Se o líder NÃO responder (caiu), este nó inicia automaticamente uma
        nova eleição. É o que garante a "recuperação" do sistema após falhas.
        """
        # Um pequeno atraso inicial diferente por nó (id) evita que todos os nós
        # detectem a falha e disparem eleições EXATAMENTE no mesmo instante.
        time.sleep(1.0 + 0.15 * self.id)

        # Mesma proteção do _loop_servidor: se o nó cair e reviver enquanto
        # esta thread dormia, uma NOVA thread de monitor foi criada — esta
        # aqui percebe que foi substituída e se encerra (evita PINGs e
        # eleições em duplicidade).
        minha_thread = threading.current_thread()
        while self.ativo and self._thread_monitor is minha_thread:
            time.sleep(1.5)
            if not self.ativo or self._thread_monitor is not minha_thread:
                break

            lider = self.lider_conhecido
            # Nada a fazer se: não há líder definido, ou EU sou o líder.
            if lider is None or lider == self.id:
                continue

            endereco = self._endereco_de(lider)
            if endereco is None:
                continue

            # PING no líder, esperando um PONG de volta.
            resposta = enviar_mensagem(endereco["host"], endereco["porta"],
                                       {"tipo": MSG_PING}, esperar_resposta=True)
            if resposta is None:
                # Líder não respondeu -> caiu.
                self.log(f"⚠️  Nó {self.id} detectou que o líder (nó {lider}) caiu!",
                         tipo="falha")
                # Zera o líder conhecido para não disparar várias eleições seguidas.
                self.lider_conhecido = None
                # Garante que só UM nó inicia a eleição: vários monitores podem
                # detectar a falha quase ao mesmo tempo (dentro da janela de 1,5s),
                # e cada um chamaria iniciar_eleicao em paralelo — causando múltiplas
                # setas simultâneas no anel que pareciam "aleatórias". Com o lock,
                # o check-and-set é atômico: só o primeiro que vê False sobe o flag
                # e dispara a eleição; os demais veem True e ficam aguardando.
                with self.rede.lock:
                    ja_em_curso = self.rede.eleicao_em_andamento
                    if not ja_em_curso:
                        self.rede.eleicao_em_andamento = True
                if not ja_em_curso:
                    election.iniciar_eleicao(self)

    # ------------------------------------------------------------------ #
    # AUXILIARES usados pelo algoritmo (election.py) e pela interface     #
    # ------------------------------------------------------------------ #

    def indice_no_anel(self):
        """Devolve a posição (índice) deste nó dentro da lista do anel."""
        for i, n in enumerate(self.anel):
            if n["id"] == self.id:
                return i
        return -1

    def _endereco_de(self, id_no):
        """Procura, no anel, o endereço (host/porta) de um nó pelo id."""
        for n in self.anel:
            if n["id"] == id_no:
                return n
        return None

    def marcar_transito(self, de_id, para_id, mensagem):
        """Registra que uma mensagem está viajando de->para (para a animação).

        Guarda também o conteúdo da mensagem (ids coletados ou líder anunciado)
        para que a interface possa mostrar — fica claro O QUE está sendo enviado.

        Os trânsitos ficam num DICIONÁRIO indexado pelo nó remetente, não num
        slot único: quando duas mensagens circulam ao mesmo tempo (ex.: dois
        nós detectam a queda do líder e disparam eleições em paralelo), um slot
        único fazia uma thread APAGAR o voo da outra — a bolinha/seta sumia do
        anel no meio do salto. Com um trânsito por remetente, cada nó só mexe
        no seu, e a interface desenha todos os voos simultâneos.
        """
        with self.rede.lock:
            self.rede.transitos[self.id] = {
                "de": de_id,
                "para": para_id,
                "tipo": mensagem.get("tipo"),
                "ids": list(mensagem.get("ids", [])),
                "lider": mensagem.get("lider"),
                # Instante em que o "voo" começou. A interface usa isso para
                # retomar a animação do ponto certo a cada atualização, em vez
                # de reiniciá-la do zero (o que fazia a bolinha "teleportar").
                "inicio": time.time(),
            }

    def limpar_transito(self):
        """Apaga o registro de mensagem em trânsito DESTE nó (só o dele)."""
        with self.rede.lock:
            self.rede.transitos.pop(self.id, None)

    def log(self, texto, tipo="info"):
        """Adiciona uma linha à linha do tempo compartilhada (e ao terminal)."""
        linha = {"hora": agora(), "no": self.id, "tipo": tipo, "texto": texto}
        with self.rede.lock:
            self.rede.logs.append(linha)
        if self.imprimir:
            print(f"[{linha['hora']}] (nó {self.id}) {texto}")

    def snapshot(self):
        """Devolve um retrato do estado atual do nó (para a interface/cliente)."""
        return {
            "id": self.id,
            "porta": self.porta,
            "ativo": self.ativo,
            "eh_lider": self.eh_lider,
            "lider_conhecido": self.lider_conhecido,
        }


class Rede:
    """
    Cria e gerencia um ANEL de nós.

    Guarda objetos compartilhados entre todos os nós:
      - logs     : a linha do tempo única de eventos (para exibir na interface);
      - transitos: as mensagens viajando agora, uma por nó remetente
                   (para destacar na animação — pode haver mais de uma);
      - lock     : trava para acessar logs/transitos com segurança entre threads.
    """

    def __init__(self, ids, host="127.0.0.1", porta_base=5001, passo_delay=0.6):
        self.host = host
        self.lock = threading.Lock()
        self.logs = []                       # linha do tempo compartilhada
        self.transitos = {}                  # {id do remetente: mensagem em voo}
        self.eleicao_em_andamento = False    # útil para a interface saber o estado

        # Monta o "mapa do anel": a ordem desta lista É a ordem do anel.
        # Aqui a ordem segue os ids informados; cada nó conhece todos os endereços.
        self.anel = [
            {"id": id, "host": host, "porta": porta_base + i}
            for i, id in enumerate(ids)
        ]

        # Cria os nós (ainda desligados).
        self.nos = {
            n["id"]: Node(n["id"], host, n["porta"], self.anel, self,
                          passo_delay=passo_delay)
            for n in self.anel
        }

    # --- Operações de alto nível usadas pela interface Streamlit ---

    def iniciar_todos(self):
        """Liga todos os nós do anel."""
        for no in self.nos.values():
            no.iniciar()

    def parar_todos(self):
        """Desliga todos os nós (encerra a demonstração)."""
        for no in self.nos.values():
            no.derrubar()

    def derrubar(self, id_no):
        """Simula a falha de um nó específico."""
        self.nos[id_no].derrubar()

    def reviver(self, id_no):
        """Religa um nó que havia caído e reinicia a eleição para ressincronizar o anel."""
        self.nos[id_no].reviver()
        no = self.nos[id_no]
        if no.ativo:
            self.iniciar_eleicao_em(id_no)

    def iniciar_eleicao_em(self, id_no):
        """Pede a um nó específico que comece uma eleição (acionado pela interface)."""
        self.eleicao_em_andamento = True
        # Roda em uma thread para não travar a interface durante a circulação.
        threading.Thread(target=election.iniciar_eleicao,
                         args=(self.nos[id_no],), daemon=True).start()

    def estados(self):
        """Retorna a lista de snapshots de todos os nós (ordem do anel)."""
        return [self.nos[n["id"]].snapshot() for n in self.anel]

    def lider_atual(self):
        """Descobre quem é o líder atualmente (entre os nós que se dizem líder)."""
        for n in self.anel:
            no = self.nos[n["id"]]
            if no.ativo and no.eh_lider:
                return no.id
        return None
