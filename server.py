"""
server.py
=========
Executa UM nó do anel como um PROCESSO independente (um terminal por nó).

Use este arquivo quando quiser mostrar o sistema REALMENTE distribuído, com
vários processos conversando por sockets — sem o Streamlit. Cada processo é um
servidor que escuta em sua porta e repassa mensagens ao próximo nó vivo.

Exemplo (abra 3 terminais e rode um comando em cada):

    python3 server.py --id 1 --anel 1:5001,2:5002,3:5003
    python3 server.py --id 2 --anel 1:5001,2:5002,3:5003
    python3 server.py --id 3 --anel 1:5001,2:5002,3:5003

Depois, em um quarto terminal, dispare a eleição inicial com o cliente:

    python3 client.py --porta 5001 --comando eleicao

Para simular a falha do líder, basta apertar Ctrl+C no terminal dele:
os demais detectam a queda e iniciam uma nova eleição automaticamente.
"""

import argparse
import threading
import time

from node import Node


class _RedeShim:
    """
    Mini "Rede" para o modo de processo único.

    A classe Node espera um objeto `rede` que ofereça: lock, logs, transito e
    eleicao_em_andamento. No modo Streamlit isso vem da classe Rede; aqui, como
    há só UM nó por processo, criamos esta versão mínima.
    """
    def __init__(self):
        self.lock = threading.Lock()
        self.logs = []
        self.transito = None
        self.eleicao_em_andamento = False


def _parse_anel(texto):
    """Converte 'id:porta,id:porta,...' na lista de dicionários do anel."""
    anel = []
    for item in texto.split(","):
        id_str, porta_str = item.split(":")
        anel.append({"id": int(id_str), "host": "127.0.0.1", "porta": int(porta_str)})
    return anel


def main():
    parser = argparse.ArgumentParser(description="Nó do anel de eleição (1 processo).")
    parser.add_argument("--id", type=int, required=True, help="id deste nó (inteiro).")
    parser.add_argument("--anel", required=True,
                        help="anel completo no formato id:porta,id:porta,...")
    parser.add_argument("--delay", type=float, default=0.6,
                        help="atraso por salto, em segundos (default 0.6).")
    parser.add_argument("--iniciar-eleicao", action="store_true",
                        help="este nó dispara uma eleição alguns segundos após subir.")
    args = parser.parse_args()

    anel = _parse_anel(args.anel)
    endereco = next(n for n in anel if n["id"] == args.id)

    rede = _RedeShim()
    no = Node(id=args.id, host=endereco["host"], porta=endereco["porta"],
              anel=anel, rede=rede, passo_delay=args.delay, imprimir=True)
    no.iniciar()

    if args.iniciar_eleicao:
        # Espera os outros nós subirem e então começa a eleição.
        def _disparar():
            time.sleep(3)
            import election
            rede.eleicao_em_andamento = True
            election.iniciar_eleicao(no)
        threading.Thread(target=_disparar, daemon=True).start()

    print(f"Nó {args.id} no ar (Ctrl+C para simular falha).")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        no.derrubar()
        print(f"\nNó {args.id} encerrado.")


if __name__ == "__main__":
    main()
