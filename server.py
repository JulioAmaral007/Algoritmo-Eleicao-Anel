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
import sys
import threading
import time

from node import Node
from utils import MSG_PING, enviar_mensagem

# No Windows o console usa cp1252 e quebra ao imprimir os emojis dos logs.
# Forçamos UTF-8 na saída para o modo "um terminal por nó" funcionar lá também.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


class _TopologiaProcesso:
    """
    Serviço de topologia/membership para o modo "um processo por nó".

    A classe Node espera um objeto `rede` que ofereça: lock, logs, transitos,
    eleicao_em_andamento e — no modelo puro — o método proximo_vivo(), que diz
    ao nó quem é o seu próximo nó vivo.

    No modo Streamlit isso vem da classe Rede (que conhece o flag `ativo` de
    todos). Aqui cada nó é um PROCESSO separado e não compartilha memória com os
    outros, então descobrimos quem está vivo SONDANDO a rede: mandamos um PING e
    quem responder PONG está vivo. O anel completo é só a CONFIGURAÇÃO inicial
    (passada em --anel); o nó em si continua conhecendo apenas o seu sucessor.
    """
    def __init__(self, anel, meu_id):
        self.anel = anel              # ordem do anel (config inicial), não é "conhecimento" do nó
        self.meu_id = meu_id
        self.lock = threading.Lock()
        self.logs = []
        self.transitos = {}
        self.eleicao_em_andamento = False

    def proximo_vivo(self, id_atual, ignorar=()):
        """
        Próximo nó vivo depois de `id_atual`, descoberto por PING.

        Mesma assinatura/contrato do Rede.proximo_vivo do modo Streamlit:
        retorna (sucessor, pulados). A diferença é que a vivacidade é testada
        pela rede (PING/PONG) em vez de um flag em memória.
        """
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
            if cid in ignorar:
                pulados.append(cid)
                continue
            # Sonda: está vivo se responder PONG ao nosso PING.
            resposta = enviar_mensagem(candidato["host"], candidato["porta"],
                                       {"tipo": MSG_PING}, esperar_resposta=True)
            if resposta is not None:
                return candidato, pulados
            pulados.append(cid)
        return None, pulados

    def maior_vivo(self, ids):
        """
        Maior id, dentre `ids`, cujo nó ainda está VIVO (ou None se nenhum).

        Mesmo contrato do Rede.maior_vivo, mas a vivacidade é testada por PING
        (processos separados não compartilham o flag `ativo`). Testamos do maior
        para o menor e devolvemos o primeiro que responder — esse é o líder.
        """
        for i in sorted(set(ids), reverse=True):
            if i == self.meu_id:
                return i  # este nó está vivo (é quem está fechando a eleição)
            end = next((n for n in self.anel if n["id"] == i), None)
            if end is None:
                continue
            resposta = enviar_mensagem(end["host"], end["porta"],
                                       {"tipo": MSG_PING}, esperar_resposta=True)
            if resposta is not None:
                return i
        return None


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

    rede = _TopologiaProcesso(anel=anel, meu_id=args.id)
    no = Node(id=args.id, host=endereco["host"], porta=endereco["porta"],
              rede=rede, passo_delay=args.delay, imprimir=True)
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
