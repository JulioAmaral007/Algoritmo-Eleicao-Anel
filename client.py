"""
client.py
=========
CLIENTE de linha de comando que conversa com um nó (servidor) por socket.

Serve para demonstrar de forma explícita a comunicação CLIENTE -> SERVIDOR
exigida no enunciado: aqui um programa externo abre uma conexão TCP com um nó
e envia um comando.

Comandos disponíveis:
  - eleicao : pede ao nó que INICIE uma eleição;
  - status  : pergunta o estado atual do nó (se é líder, quem ele acha que é o líder...);
  - ping    : verifica se o nó está vivo (responde PONG).

Exemplos:
  python3 client.py --porta 5001 --comando eleicao
  python3 client.py --porta 5002 --comando status
  python3 client.py --porta 5003 --comando ping
"""

import argparse
import sys

from utils import (
    MSG_INICIAR_ELEICAO, MSG_STATUS, MSG_PING,
    enviar_mensagem,
)

# No Windows o console usa cp1252 e quebra ao imprimir os emojis (✅/❌).
# Forçamos UTF-8 na saída, como já fazem server.py e teste_eleicao.py.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def main():
    parser = argparse.ArgumentParser(description="Cliente para falar com um nó do anel.")
    parser.add_argument("--host", default="127.0.0.1", help="endereço do nó.")
    parser.add_argument("--porta", type=int, required=True, help="porta do nó alvo.")
    parser.add_argument("--comando", required=True,
                        choices=["eleicao", "status", "ping"],
                        help="comando a enviar ao nó.")
    args = parser.parse_args()

    if args.comando == "eleicao":
        # Não esperamos resposta: o nó apenas começa a circular a eleição.
        ok = enviar_mensagem(args.host, args.porta, {"tipo": MSG_INICIAR_ELEICAO})
        if ok is None:
            print(f"❌ Não consegui falar com o nó na porta {args.porta} (está vivo?).")
        else:
            print(f"✅ Pedido de eleição enviado ao nó na porta {args.porta}.")

    elif args.comando == "status":
        resposta = enviar_mensagem(args.host, args.porta, {"tipo": MSG_STATUS},
                                   esperar_resposta=True)
        if resposta is None:
            print(f"❌ Nó na porta {args.porta} não respondeu (provavelmente caiu).")
        else:
            print("📋 Estado do nó:")
            print(f"   id ................ {resposta['id']}")
            print(f"   ativo ............. {resposta['ativo']}")
            print(f"   é líder? .......... {resposta['eh_lider']}")
            print(f"   líder conhecido ... {resposta['lider_conhecido']}")

    elif args.comando == "ping":
        resposta = enviar_mensagem(args.host, args.porta, {"tipo": MSG_PING},
                                   esperar_resposta=True)
        if resposta is None:
            print(f"❌ Sem resposta: o nó na porta {args.porta} parece estar morto.")
        else:
            print(f"✅ PONG recebido do nó {resposta['id']} (está vivo).")


if __name__ == "__main__":
    main()
