"""
utils.py
========
Funções utilitárias de BAIXO NÍVEL usadas por todo o projeto.

Aqui ficam:
  - os "tipos de mensagem" que circulam no anel;
  - a função que ENVIA uma mensagem por socket TCP;
  - a função que RECEBE uma mensagem de um socket TCP;
  - um pequeno formatador de log (com hora) para deixar a saída bonita.

A ideia é concentrar TODO o "trabalho com sockets" em um único arquivo,
para que os demais arquivos (node.py, election.py, app.py) fiquem limpos e
fáceis de ler. Quem quiser entender "como os bytes viajam na rede" lê AQUI.
Quem quiser entender "o algoritmo de eleição" lê em election.py.

Protocolo escolhido (bem simples, de propósito):
  - Cada mensagem é um dicionário Python convertido para JSON.
  - Cada mensagem é enviada terminando com '\n' (quebra de linha) — isso marca
    o "fim da mensagem" para quem está lendo.
  - Uma conexão TCP = uma mensagem (abre, envia, opcionalmente lê resposta, fecha).
    Isso é menos eficiente, mas MUITO mais fácil de explicar e depurar.
"""

import json
import socket
from datetime import datetime

# ---------------------------------------------------------------------------
# TIPOS DE MENSAGEM
# ---------------------------------------------------------------------------
# Em vez de espalhar strings soltas ("election", "coord"...) pelo código,
# damos um nome a cada tipo. Assim evitamos erros de digitação e fica claro
# quais mensagens existem no sistema.
MSG_ELECTION = "ELEICAO"        # Mensagem que circula coletando os IDs dos nós vivos.
MSG_COORDINATOR = "COORDENADOR" # Anúncio: "o novo líder é o nó X".
MSG_PING = "PING"               # "Você está vivo?" (usado para detectar falhas).
MSG_PONG = "PONG"               # Resposta ao PING: "Sim, estou vivo!".
MSG_STATUS = "STATUS"           # Pergunta o estado de um nó (usado pelo client.py).
MSG_INICIAR_ELEICAO = "INICIAR_ELEICAO"  # Pede a um nó que COMECE uma eleição (client.py).


def agora() -> str:
    """Retorna a hora atual formatada como HH:MM:SS.mmm (só para os logs)."""
    # %f dá microssegundos (6 dígitos); cortamos os 3 últimos para ficar em ms.
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def codificar(mensagem: dict) -> bytes:
    """Serializa a mensagem no formato da rede: JSON terminado em '\\n', em bytes.

    Centraliza o "formato do fio" num só lugar, usado tanto por quem ENVIA
    (enviar_mensagem) quanto por quem RESPONDE na mesma conexão (node.py).
    """
    return (json.dumps(mensagem) + "\n").encode("utf-8")


def enviar_mensagem(host: str, porta: int, mensagem: dict,
                    timeout: float = 1.0, esperar_resposta: bool = False):
    """
    Envia UMA mensagem (dicionário) para o nó que está escutando em (host, porta).

    Passo a passo do que acontece "na rede":
      1. Criamos um socket TCP.
      2. Tentamos conectar em (host, porta). Se o nó estiver MORTO, a conexão
         falha (ConnectionRefusedError) — é exatamente assim que detectamos falhas!
      3. Transformamos o dicionário em texto JSON e enviamos os bytes.
      4. (Opcional) Lemos uma resposta de volta — usado por PING e STATUS.

    Retorna:
      - o dicionário de resposta, se esperar_resposta=True e tudo deu certo;
      - True, se enviou com sucesso e não esperava resposta;
      - None, se NÃO conseguiu falar com o nó (provavelmente ele está morto).
    """
    try:
        # 'with' garante que o socket será fechado no final, mesmo se der erro.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)          # não ficamos presos para sempre esperando
            s.connect((host, porta))       # <- aqui falha se o nó estiver morto

            s.sendall(codificar(mensagem))  # serializa (JSON + '\n') e ENVIA os bytes

            if esperar_resposta:
                resposta = _ler_linha(s)   # lê a resposta do outro lado
                return json.loads(resposta) if resposta else None
            return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        # Qualquer um desses erros significa, na prática: "não consegui falar
        # com esse nó". Para o nosso algoritmo, isso quer dizer "nó indisponível".
        return None


def receber_mensagem(conexao: socket.socket):
    """
    Lê UMA mensagem completa de uma conexão já aberta (lado servidor).

    O socket do nó que está escutando recebe uma conexão; chamamos esta função
    para extrair o dicionário que o remetente enviou.
    """
    linha = _ler_linha(conexao)
    if not linha:
        return None
    return json.loads(linha)


def _ler_linha(conexao: socket.socket) -> str:
    """
    Função auxiliar: lê bytes do socket até encontrar '\n' (fim da mensagem).

    Por que isso é necessário? Porque o TCP entrega um "fluxo" de bytes, sem
    fronteiras de mensagem. Combinamos que cada mensagem termina em '\n', então
    lemos pedacinho por pedacinho até achar essa marca.
    """
    buffer = b""
    while b"\n" not in buffer:
        pedaco = conexao.recv(1024)        # lê até 1024 bytes por vez
        if not pedaco:                     # conexão fechada pelo outro lado
            break
        buffer += pedaco
    return buffer.decode("utf-8").strip()
