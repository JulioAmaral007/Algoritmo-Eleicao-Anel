"""
Teste automatizado do algoritmo de eleicao em anel (sem interface).

Execute com:  python3 teste_eleicao.py

Cobre tres cenarios:
  1. Eleicao inicial  -> o no de maior id vence.
  2. Falha do lider   -> deteccao automatica + nova eleicao.
  3. Volta do no caido -> nova eleicao manual reelege o maior id.
"""
import time
from node import Rede

# Anel com 4 nos: ids 1,2,3,4 (o maior id = 4 deve vencer)
rede = Rede(ids=[1, 2, 3, 4], porta_base=5301, passo_delay=0.05)
rede.iniciar_todos()
time.sleep(0.5)

print("\n=== ELEICAO INICIAL (disparada pelo no 1) ===")
rede.iniciar_eleicao_em(1)
time.sleep(2)
print("Lider atual:", rede.lider_atual(), "| estados:", [(s['id'], s['eh_lider']) for s in rede.estados()])
assert rede.lider_atual() == 4, "Esperava no 4 como lider"

print("\n=== FALHA DO LIDER (derrubando no 4) ===")
rede.derrubar(4)
# o monitor deve detectar e iniciar nova eleicao automaticamente
time.sleep(5)
print("Lider atual:", rede.lider_atual(), "| estados:", [(s['id'], s['ativo'], s['eh_lider']) for s in rede.estados()])
assert rede.lider_atual() == 3, "Esperava no 3 como novo lider apos falha do 4"

print("\n=== VOLTA DO NO 4 (revive) e nova eleicao manual ===")
rede.reviver(4)
time.sleep(0.5)
rede.iniciar_eleicao_em(2)
time.sleep(2)
print("Lider atual:", rede.lider_atual())
assert rede.lider_atual() == 4, "Esperava no 4 de volta como lider"

print("\n>>> TODOS OS TESTES PASSARAM <<<")
print("\n--- ultimas 12 linhas do log ---")
for l in rede.logs[-12:]:
    print(f"[{l['hora']}] no{l['no']} ({l['tipo']}): {l['texto']}")
rede.parar_todos()
