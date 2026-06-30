import time

from utils import MSG_ELECTION, MSG_COORDINATOR, enviar_mensagem


def iniciar_eleicao(no):
    no.log(f"🗳️  Nó {no.id} INICIOU uma eleição.", tipo="eleicao")
    mensagem = {
        "tipo": MSG_ELECTION,
        "ids": [no.id],
        "iniciador": no.id,
    }
    _enviar_para_sucessor_vivo(no, mensagem)


def processar_eleicao(no, mensagem):
    ids_coletados = mensagem["ids"]

    if no.id in ids_coletados:
        # Filtra só vivos: um nó pode ter entrado na lista e caído durante a circulação.
        novo_lider = no.rede.maior_vivo(ids_coletados)
        if novo_lider is None:
            novo_lider = no.id
        no.log(
            f"🔁 Eleição deu a volta completa. Candidatos: {ids_coletados}. "
            f"Maior id vivo = {novo_lider} → novo líder!",
            tipo="eleicao",
        )
        anuncio = {
            "tipo": MSG_COORDINATOR,
            "lider": novo_lider,
            "iniciador": no.id,
            "visitados": [no.id],
        }
        _aplicar_lider(no, novo_lider)
        _enviar_para_sucessor_vivo(no, anuncio)
        return

    ids_coletados.append(no.id)
    no.log(
        f"➕ Nó {no.id} entrou na disputa. Lista de candidatos agora: {ids_coletados}.",
        tipo="eleicao",
    )
    _enviar_para_sucessor_vivo(no, mensagem)


def processar_coordenador(no, mensagem):
    lider = mensagem["lider"]
    _aplicar_lider(no, lider)

    if no.id == mensagem["iniciador"]:
        no.log(
            f"✅ Anúncio do coordenador deu a volta completa. "
            f"Líder confirmado: nó {lider}. Eleição encerrada.",
            tipo="coordenador",
        )
        no.rede.eleicao_em_andamento = False
        return

    # Proteção caso o iniciador tenha caído durante o anúncio.
    if no.id in mensagem["visitados"]:
        no.rede.eleicao_em_andamento = False
        return

    mensagem["visitados"].append(no.id)
    _enviar_para_sucessor_vivo(no, mensagem)


def _aplicar_lider(no, lider_id):
    no.lider_conhecido = lider_id
    no.eh_lider = (no.id == lider_id)
    marca = " (sou eu!)" if no.eh_lider else ""
    no.log(f"👑 Nó {no.id} reconhece o nó {lider_id} como líder{marca}.",
           tipo="coordenador")


def _enviar_para_sucessor_vivo(no, mensagem):
    ignorar = set()

    while True:
        sucessor, _ = no.rede.proximo_vivo(no.id, ignorar=ignorar)
        if sucessor is None:
            no.log(f"🏝️  Nó {no.id} é o único vivo. Declara-se líder.", tipo="coordenador")
            _aplicar_lider(no, no.id)
            no.rede.eleicao_em_andamento = False
            return False

        no.sucessor = sucessor
        no.marcar_transito(no.id, sucessor["id"], mensagem)
        time.sleep(no.passo_delay)

        entregue = enviar_mensagem(sucessor["host"], sucessor["porta"], mensagem)
        no.limpar_transito()

        if entregue is not None:
            return True

        no.log(f"➡️  Sucessor (nó {sucessor['id']}) não respondeu; pulando para o próximo.",
               tipo="falha")
        ignorar.add(sucessor["id"])
