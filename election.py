"""
election.py
===========
O CÉREBRO do projeto: aqui está o ALGORITMO DE ELEIÇÃO EM ANEL.

Mantivemos a lógica do algoritmo SEPARADA do código de rede (sockets) e de
interface (Streamlit). Assim, este arquivo lê quase como uma "receita" do
algoritmo, sem ruído. As funções recebem um objeto `no` (definido em node.py)
e usam os "verbos" que esse objeto oferece (enviar para o sucessor, registrar
log, virar líder, etc.).

------------------------------------------------------------------------------
COMO FUNCIONA O ALGORITMO DE ELEIÇÃO EM ANEL (versão "coleta de IDs")
------------------------------------------------------------------------------
Imagine os nós sentados em roda (um anel lógico). Cada nó conhece o "próximo"
da roda (seu sucessor). A eleição acontece em DUAS VOLTAS:

  VOLTA 1 — Mensagem de ELEIÇÃO (coleta de candidatos):
    1. Um nó percebe que o líder caiu e INICIA a eleição.
    2. Ele cria uma mensagem de ELEIÇÃO contendo uma lista com o SEU id.
    3. Envia a mensagem para o próximo nó VIVO do anel.
    4. Cada nó que recebe a mensagem ADICIONA o próprio id à lista e repassa
       para o próximo nó vivo.
    5. Quando a mensagem chega a um nó cujo id JÁ ESTÁ na lista, sabemos que
       ela deu a volta completa no anel. Esse nó então olha a lista e escolhe
       o MAIOR id: esse é o novo líder.

  VOLTA 2 — Mensagem de COORDENADOR (anúncio do líder):
    6. O nó que fechou a volta cria uma mensagem de COORDENADOR dizendo
       "o líder é o nó X" e a envia ao redor do anel.
    7. Cada nó que recebe atualiza quem é o líder e repassa.
    8. Quando o anúncio dá a volta completa, a eleição termina e TODOS os nós
       sabem quem é o coordenador.

Por que escolher o MAIOR id? É apenas uma regra combinada (determinística):
qualquer regra serve, desde que todos usem a MESMA. Assim todos concordam no
mesmo vencedor sem precisar de um "juiz central".
"""

import time

from utils import MSG_ELECTION, MSG_COORDINATOR, enviar_mensagem


def iniciar_eleicao(no):
    """
    Passo 1 e 2: um nó decide INICIAR uma eleição.

    Cria a mensagem de ELEIÇÃO já contendo o próprio id na lista de candidatos
    e a envia para o primeiro sucessor vivo. Se descobrir que está sozinho
    (ninguém mais responde), ele se declara líder imediatamente.
    """
    no.log(f"🗳️  Nó {no.id} INICIOU uma eleição.", tipo="eleicao")

    # A lista 'ids' vai acumulando os identificadores dos nós vivos.
    # 'iniciador' guarda quem começou (útil só para fins didáticos/log).
    mensagem = {
        "tipo": MSG_ELECTION,
        "ids": [no.id],
        "iniciador": no.id,
    }
    _enviar_para_sucessor_vivo(no, mensagem)


def processar_eleicao(no, mensagem):
    """
    Passos 4 e 5: o que um nó faz ao RECEBER uma mensagem de ELEIÇÃO.

    Há dois casos:
      (A) Meu id JÁ está na lista  -> a mensagem deu a volta completa.
          Eu fecho a eleição: escolho o maior id e começo o anúncio do líder.
      (B) Meu id NÃO está na lista -> apenas me adiciono e repasso adiante.
    """
    ids_coletados = mensagem["ids"]

    # CASO (A): a volta se completou (a mensagem voltou para alguém já listado).
    if no.id in ids_coletados:
        # A regra é "vence o MAIOR id", mas só entre os que AINDA estão vivos.
        # Sem esse filtro, um nó que entrou na lista e caiu DURANTE a eleição
        # podia ser "eleito morto" — e o anel ficava preso, pois o sucessor de
        # todos passa a pular o líder morto e ninguém o monitora. Confirmamos a
        # vivacidade com a camada de topologia antes de coroar.
        novo_lider = no.rede.maior_vivo(ids_coletados)
        if novo_lider is None:
            novo_lider = no.id   # defensivo: ao menos este nó (que fecha) está vivo
        no.log(
            f"🔁 Eleição deu a volta completa. Candidatos: {ids_coletados}. "
            f"Maior id vivo = {novo_lider} → novo líder!",
            tipo="eleicao",
        )
        # Começamos a VOLTA 2: anunciar o coordenador a todos.
        anuncio = {
            "tipo": MSG_COORDINATOR,
            "lider": novo_lider,
            "iniciador": no.id,    # quem começou o anúncio (para detectar a volta)
            "visitados": [no.id],  # nós que já receberam o anúncio (evita loop infinito)
        }
        # Eu mesmo já reconheço o novo líder antes de repassar o anúncio.
        _aplicar_lider(no, novo_lider)
        _enviar_para_sucessor_vivo(no, anuncio)
        return

    # CASO (B): ainda não passei por aqui — entro na disputa e repasso.
    ids_coletados.append(no.id)
    no.log(
        f"➕ Nó {no.id} entrou na disputa. Lista de candidatos agora: {ids_coletados}.",
        tipo="eleicao",
    )
    _enviar_para_sucessor_vivo(no, mensagem)


def processar_coordenador(no, mensagem):
    """
    Passos 7 e 8: o que um nó faz ao RECEBER o anúncio de COORDENADOR.

    Atualiza quem é o líder e repassa o anúncio, até que ele dê a volta completa
    (ou seja, retorne a quem o iniciou) — então a eleição termina.
    """
    lider = mensagem["lider"]
    _aplicar_lider(no, lider)

    # O anúncio voltou para quem o iniciou? Então a volta acabou: encerramos.
    if no.id == mensagem["iniciador"]:
        no.log(
            f"✅ Anúncio do coordenador deu a volta completa. "
            f"Líder confirmado: nó {lider}. Eleição encerrada.",
            tipo="coordenador",
        )
        no.rede.eleicao_em_andamento = False
        return

    # Proteção contra loop infinito (caso o iniciador tenha caído no meio).
    if no.id in mensagem["visitados"]:
        no.rede.eleicao_em_andamento = False
        return

    mensagem["visitados"].append(no.id)
    _enviar_para_sucessor_vivo(no, mensagem)


# ---------------------------------------------------------------------------
# FUNÇÕES AUXILIARES (privadas) — começam com "_"
# ---------------------------------------------------------------------------

def _aplicar_lider(no, lider_id):
    """Atualiza, no nó, quem é o líder atual e se ele próprio é o líder."""
    no.lider_conhecido = lider_id
    no.eh_lider = (no.id == lider_id)
    marca = " (sou eu!)" if no.eh_lider else ""
    no.log(f"👑 Nó {no.id} reconhece o nó {lider_id} como líder{marca}.",
           tipo="coordenador")


def _enviar_para_sucessor_vivo(no, mensagem):
    """
    Envia a mensagem para o SUCESSOR do nó (o próximo nó vivo do anel).

    MODELO PURO: o nó não conhece o anel inteiro. Ele pergunta ao serviço de
    topologia quem é o seu próximo nó vivo e envia SÓ para ele — um salto de
    cada vez. Se esse sucessor cair bem na hora do envio (a conexão falha),
    pedimos o PRÓXIMO vivo (ignorando o que falhou) e tentamos de novo. Assim a
    mensagem continua circulando mesmo com nós caindo durante a eleição.

    Retorna True se conseguiu entregar a alguém; False se ninguém mais respondeu
    (nesse caso, o nó está sozinho e se declara líder).
    """
    ignorar = set()

    while True:
        # Pergunta ao serviço de topologia quem é o próximo nó vivo (pulando os
        # que já falharam nesta tentativa). É a única informação de topologia
        # que o nó usa: o seu sucessor.
        sucessor, _ = no.rede.proximo_vivo(no.id, ignorar=ignorar)
        if sucessor is None:
            # Ninguém mais respondeu: o nó está sozinho e se declara líder.
            no.log(f"🏝️  Nó {no.id} é o único vivo. Declara-se líder.", tipo="coordenador")
            _aplicar_lider(no, no.id)
            no.rede.eleicao_em_andamento = False
            return False

        # Passa a conhecer este sucessor (é o vizinho que o nó guarda).
        no.sucessor = sucessor

        # Marca o "trânsito" da mensagem para a animação na interface...
        no.marcar_transito(no.id, sucessor["id"], mensagem)
        time.sleep(no.passo_delay)   # ...e dá um tempinho para o olho humano ver.

        entregue = enviar_mensagem(sucessor["host"], sucessor["porta"], mensagem)
        no.limpar_transito()

        if entregue is not None:
            return True  # entregamos ao sucessor vivo: missão cumprida.

        # Sucessor caiu bem na hora: ignora-o e pede o próximo vivo.
        no.log(f"➡️  Sucessor (nó {sucessor['id']}) não respondeu; pulando para o próximo.",
               tipo="falha")
        ignorar.add(sucessor["id"])
