"""
app.py  —  versão híbrida
Interface visual (Streamlit) com design do protótipo + backend Python real.
Nós TCP reais via node.py / election.py / utils.py.

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

# ── paleta ────────────────────────────────────────────────────────────────────
BG      = "#0a1020"
PANEL   = "#111a2e"
PANEL2  = "#0d1525"
PANEL3  = "#0b121f"
BORDER  = "#213050"
BORDERS = "#18233c"
TEXT    = "#e8edf7"
MUTED   = "#93a1bd"
FAINT   = "#5e6c89"
BLUE    = "#3f8cff"
BLUE2   = "#6aa6ff"
BLUEBG  = "rgba(63,140,255,.14)"
GOLD    = "#f3b73c"
GOLD2   = "#ffd57a"
GREEN   = "#34d399"
RED     = "#f0563f"
RED2    = "#ff7a66"
EDGE    = "#2e3e60"

# ── página ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Eleição em Anel — Grupo 8",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(f"""
<style>
  [data-testid="stAppViewContainer"], .stApp {{ background: {BG} !important; }}
  section.main {{ background: {BG}; }}

  [data-testid="stSidebar"] {{
    background: {PANEL} !important;
    border-right: 1px solid {BORDERS} !important;
    transform: none !important;
    visibility: visible !important;
    pointer-events: auto !important;
    width: 300px !important;
    min-width: 300px !important;
    max-width: 300px !important;
  }}
  [data-testid="stSidebar"] > div {{ padding-top: 1rem; }}

  header,
  #MainMenu, footer,
  [data-testid="stDecoration"],
  [data-testid="stStatusWidget"],
  [data-testid="stToolbar"],
  [data-testid="collapsedControl"] {{ display: none !important; }}

  .block-container {{
    padding: 1.2rem 1.5rem 0 !important;
    max-width: 100% !important;
  }}

  [data-testid="stSlider"] label {{
    color: {MUTED} !important;
    font-size: 12.5px !important;
  }}

  [data-baseweb="select"] > div:first-child {{
    background: {PANEL3} !important;
    border-color: {BORDER} !important;
    color: {TEXT} !important;
    border-radius: 9px !important;
    font-size: 13px !important;
  }}
  [data-baseweb="popover"],
  [data-baseweb="popover"] ul {{
    background: {PANEL} !important;
    border-color: {BORDER} !important;
  }}
  li[role="option"] {{ color: {TEXT} !important; font-size: 13px !important; }}
  li[role="option"]:hover {{ background: {BLUEBG} !important; }}

  .stButton > button {{
    border-radius: 10px !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    transition: .14s !important;
  }}
  .stButton > button[kind="primary"] {{
    background: {RED} !important;
    border-color: {RED} !important;
    color: #fff !important;
  }}
  .stButton > button[kind="primary"]:hover {{
    background: {RED2} !important;
    border-color: {RED2} !important;
  }}
  .stButton > button[kind="secondary"] {{
    background: {PANEL3} !important;
    border-color: {BORDER} !important;
    color: {TEXT} !important;
  }}
  .stButton > button[kind="secondary"]:hover {{
    border-color: {BLUE} !important;
    background: {BLUEBG} !important;
  }}

  [data-testid="stCheckbox"] label {{
    color: {TEXT} !important;
    font-size: 13px !important;
  }}

  [data-testid="stVerticalBlockBorderWrapper"] {{
    background: {PANEL} !important;
    border: 1px solid {BORDERS} !important;
    border-radius: 14px !important;
  }}

  iframe {{ border: none !important; display: block; }}

  .timeline-scroll::-webkit-scrollbar {{ width: 7px; }}
  .timeline-scroll::-webkit-scrollbar-thumb {{ background: #233252; border-radius: 99px; }}
  .timeline-scroll::-webkit-scrollbar-track {{ background: transparent; }}
</style>
""", unsafe_allow_html=True)

# ── session state ─────────────────────────────────────────────────────────────
if "rede" not in st.session_state:
    st.session_state.rede = None


@st.cache_resource
def _faixa_portas():
    # Sobrevive ao F5: session_state zera no reload, mas threads do anel antigo
    # continuam segurando as portas. O contador em cache_resource garante que
    # cada anel novo use uma faixa virgem (evita WinError 10048).
    return {"base": 6001}


def _criar_rede(n: int, delay: float, auto: bool, embaralhar: bool):
    if st.session_state.rede:
        st.session_state.rede.parar_todos()
    faixa = _faixa_portas()
    base = faixa["base"]
    faixa["base"] = base + 100
    ids = list(range(1, n + 1))
    if embaralhar:
        random.shuffle(ids)
    rede = Rede(ids=ids, porta_base=base, passo_delay=delay)
    rede.iniciar_todos()
    st.session_state.rede = rede
    if auto:
        def _go():
            time.sleep(0.9)
            rede.eleicao_em_andamento = True
            election.iniciar_eleicao(rede.nos[ids[0]])
        threading.Thread(target=_go, daemon=True).start()


# ── SVG inline do anel ────────────────────────────────────────────────────────
def _svg_anel(estados, transitos) -> str:
    n = len(estados)
    if n == 0:
        return f'<div style="background:{PANEL2};border-radius:14px;height:380px;"></div>'

    vw, vh = 680, 400
    cx, cy = vw // 2, vh // 2
    R      = min(vw, vh) * 0.33
    nr     = 34

    pos = {}
    for i, e in enumerate(estados):
        ang          = -math.pi / 2 + i * (2 * math.pi / n)
        pos[e["id"]] = (cx + R * math.cos(ang), cy + R * math.sin(ang))

    p = []

    p.append(f"""<defs>
      <marker id="ar" viewBox="0 0 10 10" refX="8" refY="5"
              markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0 0 L10 5 L0 10 z" fill="{EDGE}"/>
      </marker>
      <marker id="arh" viewBox="0 0 10 10" refX="8" refY="5"
              markerWidth="8" markerHeight="8" orient="auto-start-reverse">
        <path d="M0 0 L10 5 L0 10 z" fill="{GOLD}"/>
      </marker>
    </defs>""")

    def _linha(a, b, hot, tracejada=False):
        x1, y1 = pos[a];  x2, y2 = pos[b]
        dx, dy = x2 - x1, y2 - y1
        dist   = math.hypot(dx, dy) or 1
        ux, uy = dx / dist, dy / dist
        gap    = nr + 11
        sx, sy = x1 + ux * gap, y1 + uy * gap
        ex, ey = x2 - ux * gap, y2 - uy * gap
        color  = GOLD if hot else EDGE
        width  = "3.2" if hot else "2"
        marker = "url(#arh)" if hot else "url(#ar)"
        dash   = ' stroke-dasharray="7 6"' if tracejada else ""
        return (f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
                f'stroke="{color}" stroke-width="{width}" marker-end="{marker}"{dash}/>')

    adjacentes = set()
    for i in range(n):
        a = estados[i]["id"]
        b = estados[(i + 1) % n]["id"]
        adjacentes.add((a, b))
        hot = any(t.get("de") == a and t.get("para") == b for t in transitos)
        p.append(_linha(a, b, hot))

    for t in transitos:
        de, para = t.get("de"), t.get("para")
        if de in pos and para in pos and (de, para) not in adjacentes:
            p.append(_linha(de, para, hot=True, tracejada=True))

    for e in estados:
        x, y     = pos[e["id"]]
        dead     = not e["ativo"]
        is_lider = e["eh_lider"] and not dead
        if dead:
            ring_c, fill_c = RED,  "rgba(240,86,63,.10)"
        elif is_lider:
            ring_c, fill_c = GOLD, "rgba(243,183,60,.16)"
        else:
            ring_c, fill_c = BLUE, "rgba(63,140,255,.12)"

        if is_lider:
            p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{nr+5}" fill="none" '
                     f'stroke="{GOLD}" stroke-width="1.5" opacity="0.4"/>')

        dash = "5 5" if dead else "none"
        sw   = "2.5" if dead else "3.5"
        p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{nr}" fill="{fill_c}" '
                 f'stroke="{ring_c}" stroke-width="{sw}" stroke-dasharray="{dash}"/>')

        if dead:
            p.append(f'<text x="{x:.1f}" y="{y+1:.1f}" text-anchor="middle" '
                     f'dominant-baseline="central" font-size="24" font-weight="800" '
                     f'fill="{RED}">✕</text>')
        else:
            sub   = "LÍDER" if is_lider else "ativo"
            sub_c = GOLD2   if is_lider else "#9fb6e0"
            p.append(f'<text x="{x:.1f}" y="{y-5:.1f}" text-anchor="middle" '
                     f'dominant-baseline="central" font-size="28" font-weight="800" '
                     f'fill="#fff" font-family="ui-monospace,monospace">{e["id"]}</text>')
            p.append(f'<text x="{x:.1f}" y="{y+17:.1f}" text-anchor="middle" '
                     f'font-size="11" font-weight="700" letter-spacing="0.5" '
                     f'fill="{sub_c}">{sub}</text>')

    hint = (f'<text x="10" y="16" font-size="10" fill="{FAINT}" '
            f'font-family="ui-monospace,monospace">as setas mostram o sentido das mensagens</text>')

    svg = (f'<svg viewBox="0 0 {vw} {vh}" style="width:100%;display:block;">'
           + hint + "".join(p) + "</svg>")

    return (f'<div style="background:{PANEL2};border:1px solid {BORDERS};'
            f'border-radius:14px;overflow:hidden;">{svg}</div>')


# ── banner de fase e linha do tempo (helpers de renderização) ──────────────────
def _banner_fase(em_curso, tp, transito, lider, qtd_ativos):
    GOLD_BG = "rgba(243,183,60,.07)"
    if em_curso and tp == "ELEICAO" and transito:
        return ("Fase 1 — Eleição",
                f"ELEICAO de nó {transito['de']} → nó {transito['para']}. "
                f"Ids coletados: {transito.get('ids', [])}.",
                GOLD, GOLD_BG, GOLD2)
    if em_curso and tp == "COORDENADOR" and transito:
        return ("Fase 2 — Coordenador",
                f"COORDENADOR de nó {transito['de']} → nó {transito['para']}, "
                f"líder = nó {transito.get('lider')}.",
                GOLD, GOLD_BG, GOLD2)
    if em_curso and tp == "ELEICAO":
        return ("Fase 1 — Eleição",
                "A mensagem circula pelo anel coletando ids — o maior vence.",
                GOLD, GOLD_BG, GOLD2)
    if em_curso and tp == "COORDENADOR":
        return ("Fase 2 — Coordenador",
                "O anúncio do novo líder está circulando pelo anel.",
                GOLD, GOLD_BG, GOLD2)
    if em_curso:
        return ("Eleição em andamento",
                "A mensagem circula pelo anel coletando ids — o maior vence.",
                GOLD, GOLD_BG, GOLD2)
    if lider:
        return (f"Estável — líder: nó {lider}",
                f"Todos os {qtd_ativos} nós reconhecem o nó {lider}. "
                f"Derrube o líder para forçar nova eleição.",
                GREEN, "rgba(52,211,153,.07)", GREEN)
    return ("Anel pronto",
            "Inicie uma eleição manualmente ou use a eleição automática.",
            BLUE, "rgba(63,140,255,.07)", BLUE2)


def _timeline_html(logs) -> str:
    kind_c = {
        "eleicao": GOLD, "coordenador": BLUE,
        "falha": RED, "sistema": MUTED, "info": MUTED,
    }
    rows = []
    for ev in reversed(logs[-80:]):
        cor = kind_c.get(ev.get("tipo", "info"), MUTED)
        rows.append(f"""
        <div style="background:{PANEL3};border:1px solid {BORDERS};
          border-left:3px solid {cor};border-radius:4px 9px 9px 4px;padding:7px 11px;">
          <div style="font-size:9.5px;color:{FAINT};margin-bottom:2px;
                      font-family:ui-monospace,monospace;">
            [{ev['hora']}] · <span style="color:{BLUE2};">nó {ev['no']}</span>
          </div>
          <div style="font-size:11px;color:#cdd7ea;line-height:1.45;
                      font-family:ui-monospace,monospace;">{ev['texto']}</div>
        </div>""")

    empty = (f'<div style="color:{FAINT};font-size:12px;text-align:center;padding:40px 10px;">'
             f'Os eventos aparecerão aqui em tempo real.</div>')

    # st.markdown interpreta Markdown: linha em branco encerra o bloco HTML e
    # linhas com 4+ espaços viram código. Colapsamos em uma linha para evitar isso.
    html = (
        f'<div style="background:{PANEL};border:1px solid {BORDERS};'
        f'border-radius:14px;padding:13px;">'
        f'<div style="display:flex;align-items:center;'
        f'justify-content:space-between;margin-bottom:10px;">'
        f'<span style="font-size:10.5px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:.08em;color:{MUTED};">Linha do tempo</span>'
        f'<span style="font-size:10px;color:{FAINT};'
        f'font-family:ui-monospace,monospace;">{len(logs)} eventos</span>'
        f'</div>'
        f'<div class="timeline-scroll" style="height:620px;overflow-y:auto;'
        f'display:flex;flex-direction:column;gap:7px;">'
        f'{"".join(rows) if rows else empty}'
        f'</div></div>'
    )
    return "".join(line.strip() for line in html.splitlines())


# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style="margin-bottom:16px;padding-bottom:13px;border-bottom:1px solid {BORDERS};">
      <div style="font-weight:800;font-size:20px;color:{TEXT};">Eleição em Anel</div>
      <div style="font-size:14px;color:{MUTED};margin-top:2px;">Grupo 8 · UFSC Araranguá</div>
    </div>
    <div style="font-size:11px;font-weight:700;text-transform:uppercase;
                letter-spacing:.08em;color:{MUTED};margin-bottom:10px;">
      Configuração do anel
    </div>
    """, unsafe_allow_html=True)

    qtd        = st.slider("Quantidade de nós",     3, 8,   5, key="qtd")
    delay      = st.slider("Atraso por salto (s)", 0.2, 1.5, 0.6, 0.05, key="delay")
    auto       = st.checkbox("Eleição inicial automática", value=True,  key="auto")
    embaralhar = st.checkbox("Embaralhar ids no anel",     value=False, key="emb")

    if st.button("Criar anel / Reiniciar", type="primary",
                 use_container_width=True, key="btn_criar"):
        _criar_rede(qtd, delay, auto, embaralhar)
        st.rerun()

    rede = st.session_state.rede
    if rede and st.button("Parar tudo", use_container_width=True, key="btn_parar"):
        rede.parar_todos()
        st.session_state.rede = None
        st.rerun()

    st.markdown(f"""
    <div style="height:1px;background:{BORDERS};margin:12px 0;"></div>
    <div style="font-size:11px;font-weight:700;text-transform:uppercase;
                letter-spacing:.08em;color:{MUTED};margin-bottom:10px;">
      Como ler o anel
    </div>
    <div style="display:flex;flex-direction:column;gap:9px;">
      <div style="display:flex;align-items:center;gap:9px;font-size:12px;color:{MUTED};">
        <span style="width:11px;height:11px;border-radius:50%;background:{GOLD};flex:none;"></span>
        <span><b style="color:{TEXT};">Dourado</b> = líder atual</span>
      </div>
      <div style="display:flex;align-items:center;gap:9px;font-size:12px;color:{MUTED};">
        <span style="width:11px;height:11px;border-radius:50%;background:{BLUE};flex:none;"></span>
        <span><b style="color:{TEXT};">Azul</b> = nó ativo</span>
      </div>
      <div style="display:flex;align-items:center;gap:9px;font-size:12px;color:{MUTED};">
        <span style="color:{RED};font-weight:900;width:11px;text-align:center;flex:none;">✕</span>
        <span><b style="color:{TEXT};">Vermelho</b> = nó caído</span>
      </div>
      <div style="display:flex;align-items:center;gap:9px;font-size:12px;color:{MUTED};">
        <span style="color:{GOLD};font-weight:900;flex:none;">→</span>
        <span>seta dourada = <b style="color:{TEXT};">mensagem em trânsito</b></span>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ── layout principal ──────────────────────────────────────────────────────────
rede = st.session_state.rede

if rede is None:
    st.markdown(f"""
    <div style="background:{PANEL};border:1px solid {BORDERS};border-radius:14px;
                padding:48px;text-align:center;margin-top:8px;">
      <div style="font-size:13px;color:{MUTED};">
        Clique em <b style="color:{TEXT};">Criar anel / Reiniciar</b>
        na barra lateral para começar.
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()


# 0.25s: menor que o passo_delay mínimo (0.2s), para nenhum salto passar despercebido.
@st.fragment(run_every=0.25)
def _live():
    estados = rede.estados()
    with rede.lock:
        transitos = [dict(t) for t in rede.transitos.values()]
        logs      = list(rede.logs)
    transito = max(transitos, key=lambda t: t.get("inicio", 0)) if transitos else None

    lider       = rede.lider_atual()
    em_curso    = rede.eleicao_em_andamento
    ativos      = [e for e in estados if e["ativo"]]
    mortos      = [e for e in estados if not e["ativo"]]
    qtd_ativos  = len(ativos)

    col_ring, col_log = st.columns([1.9, 1.3])

    with col_ring:
        tp = transito.get("tipo") if transito else None
        if em_curso:
            if tp:
                st.session_state.fase_atual = tp
            else:
                # "Memória" de fase: sem isso o banner pisca entre "Fase 1/2" e o
                # texto genérico enquanto a mensagem viaja entre dois saltos.
                tp = st.session_state.get("fase_atual")
        else:
            st.session_state.fase_atual = None

        b_main, b_sub, bb_bdr, bb_bg, bb_mc = _banner_fase(
            em_curso, tp, transito, lider, qtd_ativos)

        st.markdown(f"""
        <div style="background:{bb_bg};border-left:3px solid {bb_bdr};
                    border-radius:4px 14px 14px 4px;padding:11px 16px;margin-bottom:12px;">
          <div style="font-weight:700;font-size:14px;color:{bb_mc};">{b_main}</div>
          <div style="font-size:12px;color:{MUTED};margin-top:3px;line-height:1.5;">{b_sub}</div>
        </div>
        """, unsafe_allow_html=True)

        ids_ativos = [e["id"] for e in ativos]
        ids_mortos = [e["id"] for e in mortos]

        cb, cc = st.columns(2)
        with cb:
            with st.container(border=True):
                st.markdown(f'<div style="font-size:11.5px;font-weight:700;color:{RED2};">'
                            f'Derrubar um nó</div>', unsafe_allow_html=True)
                if ids_ativos:
                    kill_fmt = {x: f"Nó {x}" + (" (líder)" if x == lider else "")
                                for x in ids_ativos}
                    kill = st.selectbox("_kill", ids_ativos,
                                        format_func=lambda x: kill_fmt[x],
                                        key="sel_kill", label_visibility="collapsed")
                    if st.button("Derrubar", use_container_width=True, key="btn_kill"):
                        rede.derrubar(kill)
                else:
                    st.caption("Nenhum nó ativo.")

        with cc:
            with st.container(border=True):
                st.markdown(f'<div style="font-size:11.5px;font-weight:700;color:{GREEN};">'
                            f'Reviver um nó</div>', unsafe_allow_html=True)
                if ids_mortos:
                    rev = st.selectbox("_rev", ids_mortos,
                                       format_func=lambda x: f"Nó {x}",
                                       key="sel_rev", label_visibility="collapsed")
                    if st.button("Reviver", use_container_width=True, key="btn_rev"):
                        rede.reviver(rev)
                else:
                    st.caption("Nenhum nó caído.")

        st.markdown("<div style='margin:4px 0;'></div>", unsafe_allow_html=True)
        st.markdown(_svg_anel(estados, transitos), unsafe_allow_html=True)

    with col_log:
        st.markdown(_timeline_html(logs), unsafe_allow_html=True)


_live()
