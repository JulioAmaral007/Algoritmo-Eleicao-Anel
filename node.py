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
  - thread do monitor     -> de tempos em tempos verifica se o SEU SUCESSOR está
                             vivo (detecção de falha). Se o sucessor cair, o anel
                             se reconfigura; e, se quem caiu era o líder, dispara
                             automaticamente uma nova eleição.

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

    def __init__(self, id, host, porta, rede, passo_delay=0.6, imprimir=False):
        # --- Identidade e topologia ---
        self.id = id                  # identificador único (inteiro). MAIOR id vence.
        self.host = host              # endereço (localhost na demo)
        self.porta = porta            # porta TCP onde este nó escuta
        # MODELO PURO DO ANEL: o nó conhece APENAS o seu sucessor (o próximo nó
        # vivo). Ele NÃO guarda a lista de todos os nós do anel. Quando precisa
        # saber quem é o próximo — ao subir, ao encaminhar uma mensagem ou ao
        # detectar que o sucessor caiu — ele PERGUNTA ao serviço de topologia/
        # membership (self.rede), que devolve só o sucessor. A cada instante o
        # estado do nó guarda um único vizinho conhecido: self.sucessor.
        self.sucessor = None          # {id, host, porta} do próximo nó vivo (ou None)
        self.rede = rede              # serviço de topologia + log/trânsito compartilhados

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
        # Pergunto ao serviço de topologia quem é o meu sucessor (próximo nó vivo).
        # É a ÚNICA informação de topologia que este nó guarda.
        self.sucessor, _ = self.rede.proximo_vivo(self.id)
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
        # Esquece também o sucessor: ao reviver, o nó vai perguntar de novo ao
        # serviço de topologia quem é o próximo nó vivo (pode ter mudado).
        self.sucessor = None
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
        De tempos em tempos, verifica se o SUCESSOR ainda responde.

        MODELO PURO: como o nó só conhece o seu sucessor, é só ELE que o nó
        consegue vigiar (não dá para "pingar o líder" diretamente — o nó nem
        sabe o endereço dele). Em um anel, todo nó tem exatamente um antecessor;
        logo, a queda de qualquer nó é percebida por EXATAMENTE UM vizinho: o seu
        antecessor. Em particular, a queda do líder é detectada pelo antecessor
        do líder, que então dispara a nova eleição.

        Regras ao detectar que o sucessor caiu:
          - sempre CONSERTA o anel: pede ao serviço de topologia o próximo nó
            vivo (pulando o que caiu) e adota-o como novo sucessor;
          - só INICIA uma eleição se o nó que caiu era o líder conhecido. Se um
            nó comum cai, o anel apenas se reconstrói (sem nova eleição).
        """
        # Um pequeno atraso inicial diferente por nó (id) evita disparos
        # simultâneos quando vários eventos acontecem ao mesmo tempo.
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

            sucessor = self.sucessor
            # Sem sucessor conhecido (talvez eu seja o único vivo): tento
            # descobrir um. Se ainda não houver, não há o que vigiar.
            if sucessor is None or sucessor["id"] == self.id:
                self.sucessor, _ = self.rede.proximo_vivo(self.id)
                continue

            # PING no MEU sucessor, esperando um PONG de volta.
            resposta = enviar_mensagem(sucessor["host"], sucessor["porta"],
                                       {"tipo": MSG_PING}, esperar_resposta=True)
            if resposta is not None:
                # Sucessor vivo. Aproveito para "estabilizar" o anel: se algum nó
                # mais próximo voltou a viver (reentrou entre mim e o meu sucessor
                # atual), adoto-o como sucessor. Isso reencaixa nós revividos.
                ideal, _ = self.rede.proximo_vivo(self.id)
                if ideal is not None and ideal["id"] != sucessor["id"]:
                    self.sucessor = ideal
                continue

            # Sucessor não respondeu -> caiu.
            morto = sucessor["id"]
            # Conserta o anel: novo sucessor = próximo nó vivo, pulando o que caiu.
            # 'pulados' traz todos os nós mortos saltados nesse conserto — útil
            # para descobrir se o LÍDER estava entre eles (ex.: líder e antecessor
            # do líder caíram quase juntos; quem detecta é o nó anterior a ambos).
            novo_sucessor, pulados = self.rede.proximo_vivo(self.id, ignorar={morto})
            self.sucessor = novo_sucessor

            lider_caiu = (self.lider_conhecido is not None
                          and (self.lider_conhecido == morto
                               or self.lider_conhecido in pulados))

            if not lider_caiu:
                # Caiu um nó comum: o anel só se reconstrói, sem nova eleição.
                self.log(f"🔧 Nó {self.id} percebeu que seu sucessor (nó {morto}) caiu; "
                         f"anel reconfigurado (novo sucessor: "
                         f"{novo_sucessor['id'] if novo_sucessor else 'nenhum'}).",
                         tipo="falha")
                continue

            self.log(f"⚠️  Nó {self.id} detectou que o líder (nó {self.lider_conhecido}) caiu!",
                     tipo="falha")
            # Zera o líder conhecido para não disparar várias eleições seguidas.
            self.lider_conhecido = None
            # Garante que só UMA eleição comece, mesmo que outra ação concorrente
            # (ex.: eleição manual pela interface) aconteça ao mesmo tempo: o
            # check-and-set do flag é atômico sob o lock.
            with self.rede.lock:
                ja_em_curso = self.rede.eleicao_em_andamento
                if not ja_em_curso:
                    self.rede.eleicao_em_andamento = True
            if not ja_em_curso:
                election.iniciar_eleicao(self)

    # ------------------------------------------------------------------ #
    # AUXILIARES usados pelo algoritmo (election.py) e pela interface     #
    # ------------------------------------------------------------------ #

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
            # Único vizinho que o nó conhece (modelo puro): o seu sucessor.
            "sucessor": self.sucessor["id"] if self.sucessor else None,
        }


class Rede:
    """
    Cria e gerencia um ANEL de nós, e atua como SERVIÇO DE TOPOLOGIA/MEMBERSHIP.

    No modelo puro, cada Node conhece apenas o seu sucessor. Quem conhece a
    ordem do anel inteiro e quem está vivo é ESTA classe — uma camada de
    membership separada do algoritmo de eleição. Os nós perguntam a ela "quem é
    o meu próximo nó vivo?" (proximo_vivo) e guardam só essa resposta.

    Guarda objetos compartilhados entre todos os nós:
      - anel     : a ordem do anel (lista [{id, host, porta}, ...]) — o "mapa"
                   de membership; os nós NÃO têm cópia dele;
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

        # Cria os nós (ainda desligados). Repare: NÃO passamos o anel ao nó —
        # ele recebe só uma referência a esta Rede (serviço de topologia) e vai
        # perguntar a ela quem é o seu sucessor quando precisar.
        self.nos = {
            n["id"]: Node(n["id"], host, n["porta"], self,
                          passo_delay=passo_delay)
            for n in self.anel
        }

    # --- Serviço de TOPOLOGIA: responde "quem é o próximo nó vivo?" ---

    def proximo_vivo(self, id_atual, ignorar=()):
        """
        Devolve o PRÓXIMO nó VIVO depois de `id_atual` na ordem do anel.

        É a única forma de um nó descobrir o seu sucessor: ele não conhece o
        anel, então pergunta aqui. Nós mortos (e os listados em `ignorar`) são
        pulados.

        Retorna uma tupla (sucessor, pulados):
          - sucessor: {id, host, porta} do próximo nó vivo, ou None se `id_atual`
                      for o único vivo do anel;
          - pulados : lista dos ids saltados (mortos/ignorados) até achar o vivo.
                      Serve para o monitor saber se o LÍDER estava entre os que
                      caíram (detecção de queda do líder em falhas múltiplas).
        """
        total = len(self.anel)
        # Posição de id_atual na ordem do anel.
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
        """
        Maior id, dentre `ids`, cujo nó ainda está VIVO (ou None se nenhum).

        Usado para fechar a eleição sem eleger um nó que entrou na lista de
        candidatos mas caiu durante a circulação: filtramos pelos que ainda
        respondem (aqui, pelo flag `ativo` que esta camada conhece) e só então
        aplicamos a regra do maior id.
        """
        vivos = [i for i in ids if i in self.nos and self.nos[i].ativo]
        return max(vivos) if vivos else None

    def _reconfigurar_sucessores(self):
        """
        Recalcula o sucessor de cada nó VIVO.

        Chamado quando alguém ENTRA no anel (iniciar/reviver), para reencaixar o
        recém-chegado e atualizar quem aponta para ele. NÃO é chamado em
        derrubar(): ali deixamos o antecessor do nó que caiu manter o ponteiro
        antigo de propósito, para que o MONITOR dele perceba a queda via PING
        (é assim que a falha é detectada de verdade).
        """
        for n in self.anel:
            no = self.nos[n["id"]]
            if no.ativo:
                no.sucessor, _ = self.proximo_vivo(no.id)

    # --- Operações de alto nível usadas pela interface Streamlit ---

    def iniciar_todos(self):
        """Liga todos os nós do anel e encaixa cada um com o seu sucessor."""
        for no in self.nos.values():
            no.iniciar()
        # Ao subir um por um, os primeiros não tinham sucessor ainda (eram os
        # únicos vivos). Agora que todos estão de pé, fechamos o anel.
        self._reconfigurar_sucessores()

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
            # O nó voltou: reencaixa-o no anel (atualiza o sucessor de quem
            # agora deve apontar para ele) antes de ressincronizar a eleição.
            self._reconfigurar_sucessores()
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
