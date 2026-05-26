"""
app.py
======
INTERFACE VISUAL (Streamlit) do Algoritmo de Eleição em Anel.

Esta é a "tela" que usamos para APRESENTAR o algoritmo em aula. Ela permite:
  - criar o anel e iniciar todos os nós;
  - ver o anel desenhado, com o LÍDER destacado (coroa) e os nós CAÍDOS em vermelho;
  - DERRUBAR um nó (simular falha) e REVIVÊ-LO;
  - INICIAR uma eleição manualmente, escolhendo quem começa;
  - acompanhar as MENSAGENS circulando (uma bolinha viaja pela aresta do anel);
  - ler a LINHA DO TEMPO (logs) de tudo o que acontece, em tempo real.

Toda a lógica de rede e do algoritmo está em node.py / election.py / utils.py.
Aqui cuidamos apenas de mostrar o estado e oferecer os botões.

Para executar:
    streamlit run app.py
"""

import math
import random
import threading
import time

import streamlit as st

import election
from node import Rede

# --------------------------------------------------------------------------- #
# CONFIGURAÇÃO DA PÁGINA                                                       #
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Eleição em Anel — Grupo 8",
                   page_icon="🔵", layout="wide")

# Cores usadas tanto no desenho do anel quanto nas legendas.
COR_ATIVO = "#38bdf8"       # azul-céu: nó ativo
COR_LIDER = "#fbbf24"       # âmbar/dourado: o líder
COR_MORTO = "#ef4444"       # vermelho: nó caído
COR_ARESTA = "#334155"      # cinza-azulado: arestas do anel
COR_FUNDO = "#0e1525"       # fundo escuro do "painel de controle"


# --------------------------------------------------------------------------- #
# ESTADO PERSISTENTE (sobrevive aos reruns do Streamlit)                       #
# --------------------------------------------------------------------------- #
# O Streamlit re-executa este arquivo a cada interação. Guardamos a Rede em
# st.session_state para que os nós e suas threads NÃO sejam recriados a cada vez.
if "rede" not in st.session_state:
    st.session_state.rede = None


def criar_rede(qtd_nos: int, delay: float, eleicao_inicial: bool, embaralhar: bool):
    """(Re)cria o anel com a quantidade de nós escolhida e liga todos."""
    if st.session_state.rede is not None:
        st.session_state.rede.parar_todos()
    ids = list(range(1, qtd_nos + 1))     # ids 1..N (o MAIOR vence a eleição)
    if embaralhar:
        # A ordem do anel não precisa coincidir com a ordem numérica dos ids:
        # o sucessor é definido pela posição na lista, não pelo valor do id.
        # Embaralhar evidencia que o algoritmo não depende da ordenação.
        random.shuffle(ids)
    rede = Rede(ids=ids, porta_base=6001, passo_delay=delay)
    rede.iniciar_todos()
    st.session_state.rede = rede

    if eleicao_inicial:
        # Dispara uma eleição inicial a partir do nó de menor id, após os nós subirem.
        def _disparar():
            time.sleep(0.8)
            rede.eleicao_em_andamento = True
            election.iniciar_eleicao(rede.nos[ids[0]])
        threading.Thread(target=_disparar, daemon=True).start()


# --------------------------------------------------------------------------- #
# DESENHO DO ANEL (gera um SVG dentro de um "card" escuro)                     #
# --------------------------------------------------------------------------- #
def desenhar_anel(estados, transito) -> str:
    """Monta o HTML/SVG do anel a partir do estado atual dos nós."""
    n = len(estados)
    cx, cy, R, r = 250, 250, 175, 40    # centro, raio do anel, raio do nó

    # 1) Calcula a posição (x, y) de cada nó em volta de um círculo.
    pos = {}
    for i, e in enumerate(estados):
        ang = -math.pi / 2 + i * (2 * math.pi / n)   # começa no topo, sentido horário
        pos[e["id"]] = (cx + R * math.cos(ang), cy + R * math.sin(ang))

    partes = []

    # 2) Desenha as ARESTAS do anel (de cada nó para o próximo), com seta.
    for i in range(n):
        a = estados[i]["id"]
        b = estados[(i + 1) % n]["id"]
        x1, y1 = pos[a]
        x2, y2 = pos[b]
        # encurta a linha para não entrar por dentro dos círculos dos nós
        dx, dy = x2 - x1, y2 - y1
        dist = math.hypot(dx, dy) or 1
        ux, uy = dx / dist, dy / dist
        sx, sy = x1 + ux * (r + 4), y1 + uy * (r + 4)
        ex, ey = x2 - ux * (r + 12), y2 - uy * (r + 12)
        partes.append(
            f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
            f'stroke="{COR_ARESTA}" stroke-width="2" marker-end="url(#seta)"/>'
        )

    # 3) Se há uma mensagem em trânsito, desenha a aresta destacada + bolinha viajando.
    if transito:
        de, para, tipo = transito["de"], transito["para"], transito["tipo"]
        if de in pos and para in pos:
            x1, y1 = pos[de]
            x2, y2 = pos[para]
            cor = COR_LIDER if tipo == "COORDENADOR" else COR_ATIVO
            partes.append(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="{cor}" stroke-width="4" opacity="0.9"/>'
            )
            # bolinha que percorre a aresta (animação SVG nativa)
            partes.append(
                f'<circle r="9" fill="{cor}">'
                f'<animateMotion dur="0.6s" repeatCount="indefinite" '
                f'path="M {x1:.1f} {y1:.1f} L {x2:.1f} {y2:.1f}"/></circle>'
            )
            # rótulo do tipo de mensagem + CONTEÚDO no meio da aresta
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            partes.append(
                f'<text x="{mx:.1f}" y="{my-14:.1f}" fill="{cor}" font-size="13" '
                f'font-weight="700" '
                f'font-family="IBM Plex Mono, monospace" text-anchor="middle">{tipo}</text>'
            )
            # Conteúdo da mensagem (ids coletados na Fase 1, líder anunciado na Fase 2).
            if tipo == "ELEICAO" and transito.get("ids"):
                conteudo = "ids=" + str(transito["ids"]).replace(" ", "")
            elif tipo == "COORDENADOR" and transito.get("lider") is not None:
                conteudo = f"líder={transito['lider']}"
            else:
                conteudo = ""
            if conteudo:
                partes.append(
                    f'<text x="{mx:.1f}" y="{my+2:.1f}" fill="#f8fafc" font-size="12" '
                    f'font-family="IBM Plex Mono, monospace" text-anchor="middle">{conteudo}</text>'
                )

    # 4) Desenha os NÓS por cima das arestas.
    for e in estados:
        x, y = pos[e["id"]]
        if not e["ativo"]:
            preenche, borda, traco, texto_cor, rotulo = "#1a1f2e", COR_MORTO, "4 4", "#64748b", "✖ caiu"
            coroa = ""
        elif e["eh_lider"]:
            preenche, borda, traco, texto_cor, rotulo = "#2a2410", COR_LIDER, "0", "#fde68a", "LÍDER"
            coroa = f'<text x="{x:.1f}" y="{y-r-12:.1f}" font-size="26" text-anchor="middle">👑</text>'
        else:
            preenche, borda, traco, texto_cor, rotulo = "#14283d", COR_ATIVO, "0", "#e2e8f0", "ativo"
            coroa = ""

        glow = (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r+6}" fill="none" '
                f'stroke="{COR_LIDER}" stroke-width="2" opacity="0.35"/>') if e["eh_lider"] else ""

        partes.append(coroa)
        partes.append(glow)
        partes.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{preenche}" '
            f'stroke="{borda}" stroke-width="3" stroke-dasharray="{traco}"/>'
        )
        partes.append(
            f'<text x="{x:.1f}" y="{y-2:.1f}" fill="{texto_cor}" font-size="26" '
            f'font-weight="700" text-anchor="middle" '
            f'font-family="IBM Plex Mono, monospace">{e["id"]}</text>'
        )
        partes.append(
            f'<text x="{x:.1f}" y="{y+18:.1f}" fill="{texto_cor}" font-size="11" '
            f'text-anchor="middle" font-family="IBM Plex Mono, monospace">{rotulo}</text>'
        )

    svg = f'''
    <div style="background:{COR_FUNDO};border-radius:16px;padding:8px;
                box-shadow:inset 0 0 60px rgba(56,189,248,0.08);">
      <svg viewBox="0 0 500 500" width="100%" style="max-height:480px;">
        <defs>
          <marker id="seta" markerWidth="10" markerHeight="10" refX="8" refY="3"
                  orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L0,6 L9,3 z" fill="{COR_ARESTA}"/>
          </marker>
        </defs>
        {''.join(partes)}
      </svg>
    </div>
    '''
    return svg


# --------------------------------------------------------------------------- #
# CABEÇALHO                                                                    #
# --------------------------------------------------------------------------- #
st.title("🔵 Algoritmo de Eleição em Anel")
st.caption("Grupo 8 — Sistemas Distribuídos · UFSC Araranguá · "
           "demonstração interativa do anel, da eleição e da recuperação de falhas")

with st.expander("📚 Como funciona o algoritmo (clique para abrir)", expanded=False):
    st.markdown(
        """
**Ideia central.** Os processos formam um *anel lógico* — cada nó conhece apenas
o **sucessor**. Quando o líder cai, o sistema elege um novo de forma totalmente
distribuída, sem árbitro central. Acontece em **duas voltas**.

#### 🔵 Fase 1 — Mensagem `ELEICAO` (coleta de candidatos)
1. Algum nó percebe que o líder caiu (ou recebe ordem para iniciar) e cria uma
   mensagem `ELEICAO` contendo apenas o **próprio id** em uma lista.
2. Envia a mensagem para o **próximo nó vivo** do anel.
3. Cada nó que recebe **adiciona o seu id** à lista e repassa adiante.
4. Quando a mensagem volta para um nó **cujo id já está na lista**, ela deu a
   volta completa. Esse nó olha a lista e escolhe o **maior id** como líder.

#### 👑 Fase 2 — Mensagem `COORDENADOR` (anúncio)
5. O nó que fechou a volta cria a mensagem `COORDENADOR` ("o líder é o nó X")
   e a envia ao sucessor vivo.
6. Cada nó que recebe **atualiza** quem é o líder e repassa.
7. Quando o anúncio dá a volta, **todos** os nós sabem o coordenador.

#### 🩺 Detecção de falha
Cada nó (que não é o líder) envia periodicamente um `PING` ao líder. Sem `PONG`,
conclui que o líder caiu e inicia uma nova eleição automaticamente. Se múltiplos
nós dispararem ao mesmo tempo, o resultado **converge** — todos elegem o mesmo
maior id.

> 🧠 **Por que vence o maior id?** É uma regra **determinística combinada**:
> qualquer critério serve, desde que todos usem o mesmo. Assim todos chegam
> ao mesmo vencedor sem precisar de um árbitro.
        """
    )

# --------------------------------------------------------------------------- #
# BARRA LATERAL: configuração da rede                                          #
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("⚙️ Configuração do anel")
    qtd = st.slider("Quantidade de nós", min_value=3, max_value=7, value=4,
                    help="Os ids vão de 1 até N. O nó de MAIOR id vence a eleição.")
    delay = st.slider("Atraso por salto (s)", 0.1, 1.5, 0.6, 0.1,
                      help="Quanto maior, mais devagar a mensagem viaja (melhor para explicar).")
    eleicao_inicial = st.checkbox("Fazer eleição inicial automática", value=True)
    embaralhar = st.checkbox("Embaralhar ids no anel", value=False,
                             help="A ordem do anel é independente do valor dos ids. "
                                  "Ative para deixar claro que o algoritmo não depende "
                                  "da ordenação numérica — o vencedor continua sendo o maior id.")

    if st.button("🟢 Criar anel / Reiniciar", type="primary", use_container_width=True):
        criar_rede(qtd, delay, eleicao_inicial, embaralhar)
        st.success(f"Anel com {qtd} nós criado!")

    if st.session_state.rede is not None:
        if st.button("⏹️ Parar tudo", use_container_width=True):
            st.session_state.rede.parar_todos()
            st.session_state.rede = None

    st.divider()
    st.markdown(
        "**Como ler o anel**\n\n"
        "- 👑 dourado = **líder atual**\n"
        "- 🔵 azul = nó **ativo**\n"
        "- ✖ vermelho = nó **caído**\n"
        "- bolinha viajando = **mensagem** circulando\n\n"
        "As setas mostram o sentido em que as mensagens circulam no anel."
    )

rede = st.session_state.rede

# --------------------------------------------------------------------------- #
# CORPO PRINCIPAL                                                              #
# --------------------------------------------------------------------------- #
if rede is None:
    st.info("👈 Configure e clique em **Criar anel / Reiniciar** na barra lateral para começar.")
    st.stop()

# ----- Controles de ação (fora do fragmento: cada clique re-executa o app) -----
estados = rede.estados()
ids_ativos = [e["id"] for e in estados if e["ativo"]]
ids_mortos = [e["id"] for e in estados if not e["ativo"]]

c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("**🗳️ Iniciar eleição**")
    if ids_ativos:
        iniciador = st.selectbox("Nó que inicia", ids_ativos, key="ini")
        if st.button("Iniciar eleição", use_container_width=True):
            rede.iniciar_eleicao_em(iniciador)

with c2:
    st.markdown("**🔴 Derrubar um nó (falha)**")
    if ids_ativos:
        alvo_morte = st.selectbox("Nó a derrubar", ids_ativos, key="kill")
        if st.button("Derrubar nó", use_container_width=True):
            rede.derrubar(alvo_morte)
    else:
        st.caption("Nenhum nó ativo.")

with c3:
    st.markdown("**🟢 Reviver um nó**")
    if ids_mortos:
        alvo_vida = st.selectbox("Nó a reviver", ids_mortos, key="revive")
        if st.button("Reviver nó", use_container_width=True):
            rede.reviver(alvo_vida)
    else:
        st.caption("Nenhum nó caído.")

st.divider()


def _banner_fase(em_andamento, transito, lider, qtd_ativos):
    """Decide qual banner mostrar com base no estado atual da rede.

    Retorna (titulo, descricao, cor_fundo, cor_borda). Cada estado tem cores
    distintas para o aluno identificar visualmente em que fase está.
    """
    if transito and transito.get("tipo") == "ELEICAO":
        ids = transito.get("ids") or []
        return (
            "🔵 FASE 1 — Coletando candidatos",
            f"Mensagem `ELEICAO` viajando do **nó {transito['de']}** para o "
            f"**nó {transito['para']}**. Lista de ids acumulada até agora: "
            f"`{ids}`. Cada nó adiciona o próprio id e repassa.",
            "rgba(56,189,248,0.12)", COR_ATIVO,
        )
    if transito and transito.get("tipo") == "COORDENADOR":
        return (
            "👑 FASE 2 — Anunciando o líder",
            f"Mensagem `COORDENADOR` viajando do **nó {transito['de']}** para o "
            f"**nó {transito['para']}**, comunicando que o novo líder é o "
            f"**nó {transito.get('lider')}**. Cada nó atualiza seu líder conhecido.",
            "rgba(251,191,36,0.14)", COR_LIDER,
        )
    if em_andamento:
        return (
            "🗳️  Eleição em andamento",
            "Entre saltos: a próxima mensagem está prestes a partir. "
            "Aumente o **atraso por salto** na barra lateral para ver com mais calma.",
            "rgba(148,163,184,0.10)", "#94a3b8",
        )
    if lider is not None and qtd_ativos > 0:
        return (
            f"✅ Estável — Líder atual: Nó {lider}",
            f"Todos os {qtd_ativos} nós ativos reconhecem o **nó {lider}** como líder. "
            "Derrube o líder para forçar uma nova eleição automática.",
            "rgba(34,197,94,0.10)", "#22c55e",
        )
    return (
        "⏸️  Aguardando",
        "Nenhum líder eleito ainda. Use **Iniciar eleição** acima para começar.",
        "rgba(148,163,184,0.08)", "#94a3b8",
    )


def _tabela_estados(estados, transito):
    """HTML de uma 'tabela' visual mostrando o estado conhecido por cada nó.

    Foco didático: deixar claro que após a Fase 2 TODOS convergem para o mesmo
    valor de 'líder conhecido'. Durante a eleição, alguns nós ainda têm o líder
    antigo (ou nenhum) — a tabela mostra a convergência acontecendo.
    """
    em_transito = set()
    if transito:
        em_transito = {transito.get("de"), transito.get("para")}

    cards = []
    for e in estados:
        if not e["ativo"]:
            cor_borda, badge_cor, badge_texto = COR_MORTO, "#7f1d1d", "✖ caiu"
        elif e["eh_lider"]:
            cor_borda, badge_cor, badge_texto = COR_LIDER, "#92400e", "👑 LÍDER"
        else:
            cor_borda, badge_cor, badge_texto = COR_ATIVO, "#075985", "✓ ativo"

        destaque = ("box-shadow:0 0 0 2px #f8fafc inset;"
                    if e["id"] in em_transito else "")

        lider_conhecido = e["lider_conhecido"]
        lider_txt = f"nó {lider_conhecido}" if lider_conhecido is not None else "—"

        cards.append(
            f'<div style="background:rgba(255,255,255,0.04);border-left:4px solid {cor_borda};'
            f'border-radius:0 8px 8px 0;padding:10px 12px;margin-bottom:6px;{destaque}'
            f'font-family:IBM Plex Mono,monospace;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<span style="color:#f8fafc;font-size:15px;font-weight:700;">Nó {e["id"]}</span>'
            f'<span style="background:{badge_cor};color:#f8fafc;padding:2px 8px;'
            f'border-radius:10px;font-size:11px;font-weight:600;">{badge_texto}</span>'
            f'</div>'
            f'<div style="color:#cbd5e1;font-size:12.5px;margin-top:4px;">'
            f'líder conhecido: <span style="color:#f8fafc;font-weight:600;">{lider_txt}</span>'
            f'</div></div>'
        )

    return (f'<div style="background:{COR_FUNDO};border-radius:12px;padding:10px;">'
            f'{"".join(cards)}</div>')


# ----- Painel "vivo": redesenha sozinho a cada 0.7s (anima mensagens e logs) -----
@st.fragment(run_every=0.7)
def painel_vivo():
    estados = rede.estados()
    with rede.lock:
        transito = dict(rede.transito) if rede.transito else None
        logs = list(rede.logs)

    lider = rede.lider_atual()
    em_andamento = rede.eleicao_em_andamento
    qtd_ativos = sum(1 for e in estados if e["ativo"])

    # Métricas no topo
    m1, m2, m3 = st.columns(3)
    m1.metric("👑 Líder atual", f"Nó {lider}" if lider else "—")
    m2.metric("🔵 Nós ativos", qtd_ativos)
    m3.metric("🗳️ Eleição", "em andamento…" if em_andamento else "estável")

    # Banner de fase: explica em texto o que está acontecendo neste instante.
    titulo, descricao, fundo, borda = _banner_fase(em_andamento, transito,
                                                    lider, qtd_ativos)
    st.markdown(
        f'<div style="background:{fundo};border-left:5px solid {borda};'
        f'border-radius:0 10px 10px 0;padding:12px 16px;margin:6px 0 14px 0;">'
        f'<div style="color:#f8fafc;font-size:15px;font-weight:700;margin-bottom:4px;">'
        f'{titulo}</div>'
        f'<div style="color:#e2e8f0;font-size:13px;line-height:1.5;">{descricao}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    col_anel, col_logs = st.columns([1.1, 1])

    with col_anel:
        st.components.v1.html(desenhar_anel(estados, transito), height=500)
        st.markdown("**🧭 Estado conhecido por cada nó**")
        st.caption("Após a Fase 2, todos devem mostrar o mesmo líder conhecido "
                   "— é assim que se vê a convergência do algoritmo.")
        st.components.v1.html(_tabela_estados(estados, transito),
                              height=min(420, 80 + 80 * len(estados)))

    with col_logs:
        st.markdown("**📜 Linha do tempo (logs em tempo real)**")
        cores = {"eleicao": COR_ATIVO, "coordenador": COR_LIDER,
                 "falha": COR_MORTO, "sistema": "#cbd5e1", "info": "#cbd5e1"}
        linhas_html = []
        for l in reversed(logs[-60:]):   # mais recentes no topo
            cor = cores.get(l["tipo"], "#cbd5e1")
            linhas_html.append(
                f'<div style="padding:8px 12px;border-left:4px solid {cor};margin-bottom:6px;'
                f'background:rgba(255,255,255,0.04);border-radius:0 6px 6px 0;'
                f'font-family:IBM Plex Mono,monospace;font-size:13.5px;line-height:1.45;">'
                f'<div style="color:#94a3b8;font-size:11.5px;letter-spacing:0.3px;'
                f'margin-bottom:3px;">[{l["hora"]}] · nó {l["no"]}</div>'
                f'<div style="color:#f8fafc;font-weight:500;">{l["texto"]}</div></div>'
            )
        st.components.v1.html(
            f'<div style="height:440px;overflow-y:auto;padding:8px;'
            f'background:{COR_FUNDO};border-radius:12px;">{"".join(linhas_html)}</div>',
            height=460,
        )


painel_vivo()
