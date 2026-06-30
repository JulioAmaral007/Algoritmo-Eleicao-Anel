import json
import socket
from datetime import datetime

MSG_ELECTION       = "ELEICAO"
MSG_COORDINATOR    = "COORDENADOR"
MSG_PING           = "PING"
MSG_PONG           = "PONG"
MSG_STATUS         = "STATUS"
MSG_INICIAR_ELEICAO = "INICIAR_ELEICAO"


def agora() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def codificar(mensagem: dict) -> bytes:
    return (json.dumps(mensagem) + "\n").encode("utf-8")


def enviar_mensagem(host: str, porta: int, mensagem: dict,
                    timeout: float = 1.0, esperar_resposta: bool = False):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, porta))
            s.sendall(codificar(mensagem))
            if esperar_resposta:
                resposta = _ler_linha(s)
                return json.loads(resposta) if resposta else None
            return True
    except (ConnectionRefusedError, socket.timeout, OSError, ValueError):
        return None


def receber_mensagem(conexao: socket.socket):
    try:
        linha = _ler_linha(conexao)
        if not linha:
            return None
        return json.loads(linha)
    except (OSError, ValueError):
        return None


def _ler_linha(conexao: socket.socket) -> str:
    # TCP entrega um fluxo contínuo de bytes — lemos até '\n' para delimitar mensagens.
    buffer = b""
    while b"\n" not in buffer:
        pedaco = conexao.recv(1024)
        if not pedaco:
            break
        buffer += pedaco
    return buffer.decode("utf-8").strip()
