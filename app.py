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
import streamlit.components.v1 as components
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
GOLDBG  = "rgba(243,183,60,.14)"
GREEN   = "#34d399"
GREENBG = "rgba(52,211,153,.12)"
RED     = "#f0563f"
RED2    = "#ff7a66"
REDBG   = "rgba(240,86,63,.14)"
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

  /* sidebar — sempre visível, largura fixa, não pode ser fechada */
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

  /* esconde chrome do Streamlit: header (barra preta), menus e botões de toggle da sidebar */
  header,
  #MainMenu, footer,
  [data-testid="stDecoration"],
  [data-testid="stStatusWidget"],
  [data-testid="stToolbar"],
  [data-testid="collapsedControl"] {{ display: none !important; }}

  /* padding do bloco principal */
  .block-container {{
    padding: 1.2rem 1.5rem 0 !important;
    max-width: 100% !important;
  }}

  /* sliders */
  [data-testid="stSlider"] label {{
    color: {MUTED} !important;
    font-size: 12.5px !important;
  }}

  /* selects */
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

  /* botões */
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

  /* checkboxes */
  [data-testid="stCheckbox"] label {{
    color: {TEXT} !important;
    font-size: 13px !important;
  }}

  /* container com borda */
  [data-testid="stVerticalBlockBorderWrapper"] {{
    background: {PANEL} !important;
    border: 1px solid {BORDERS} !important;
    border-radius: 14px !important;
  }}

  iframe {{ border: none !important; display: block; }}
</style>
""", unsafe_allow_html=True)

# ── session state ─────────────────────────────────────────────────────────────
if "rede" not in st.session_state:
    st.session_state.rede = None


def _criar_rede(n: int, delay: float, auto: bool, embaralhar: bool):
    if st.session_state.rede:
        st.session_state.rede.parar_todos()
    # Cada anel novo usa uma FAIXA DE PORTAS DIFERENTE. Esse é o conserto-raiz do
    # WinError 10048 ("endereço já em uso") ao reiniciar: em vez de tentar rebindar
    # as MESMAS portas (cujos sockets antigos ainda podem estar fechando no Windows),
    # simplesmente saltamos para portas livres. Não precisa de sleep nem de gambiarra.
    base = st.session_state.get("porta_base", 6001)
    st.session_state.porta_base = base + 100  # próxima criação salta de faixa
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
def _svg_anel(estados, transito, passo_delay: float) -> str:
    """SVG inline (para st.markdown) — o diff do DOM preserva animateMotion entre rerenders."""
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
      <radialGradient id="ballg" cx="38%" cy="32%" r="75%">
        <stop offset="0%"   stop-color="#fff3d2"/>
        <stop offset="45%"  stop-color="{GOLD2}"/>
        <stop offset="100%" stop-color="{GOLD}"/>
      </radialGradient>
    </defs>""")

    # arestas
    for i in range(n):
        a = estados[i]["id"]
        b = estados[(i + 1) % n]["id"]
        x1, y1 = pos[a];  x2, y2 = pos[b]
        dx, dy = x2 - x1, y2 - y1
        dist   = math.hypot(dx, dy) or 1
        ux, uy = dx / dist, dy / dist
        gap    = nr + 11
        sx, sy = x1 + ux * gap, y1 + uy * gap
        ex, ey = x2 - ux * gap, y2 - uy * gap
        hot    = transito and transito.get("de") == a and transito.get("para") == b
        color  = GOLD if hot else EDGE
        width  = "3.2" if hot else "2"
        marker = "url(#arh)" if hot else "url(#ar)"
        p.append(f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
                 f'stroke="{color}" stroke-width="{width}" marker-end="{marker}"/>')

    # nós
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

    # bolinha com animateMotion (nativa SVG — funciona em inline sem iframe)
    if transito and transito.get("de") in pos and transito.get("para") in pos:
        de, para = transito["de"], transito["para"]
        x1, y1   = pos[de];  x2, y2 = pos[para]
        dur      = max(0.3, passo_delay * 0.9)
        path     = f"M {x1:.1f},{y1:.1f} L {x2:.1f},{y2:.1f}"
        tipo     = transito.get("tipo", "")
        label    = "ELE" if tipo == "ELEICAO" else ("CRD" if tipo == "COORDENADOR" else tipo[:3])
        p.append(f"""<g>
          <circle r="16" fill="{GOLD2}" opacity="0.3">
            <animateMotion dur="{dur:.2f}s" repeatCount="indefinite"><mpath href="#bpath"/></animateMotion>
          </circle>
          <circle r="12" fill="url(#ballg)" stroke="#fff7e6" stroke-width="1.5">
            <animateMotion dur="{dur:.2f}s" repeatCount="indefinite"><mpath href="#bpath"/></animateMotion>
          </circle>
          <text text-anchor="middle" dominant-baseline="central" font-size="9"
                font-weight="800" fill="#5a3d05" font-family="ui-monospace,monospace">
            {label}
            <animateMotion dur="{dur:.2f}s" repeatCount="indefinite"><mpath href="#bpath"/></animateMotion>
          </text>
        </g>
        <defs><path id="bpath" d="{path}"/></defs>""")

    hint = (f'<text x="10" y="16" font-size="10" fill="{FAINT}" '
            f'font-family="ui-monospace,monospace">as setas mostram o sentido das mensagens</text>')

    svg = (f'<svg viewBox="0 0 {vw} {vh}" style="width:100%;display:block;">'
           + hint + "".join(p) + "</svg>")

    return (f'<div style="background:{PANEL2};border:1px solid {BORDERS};'
            f'border-radius:14px;overflow:hidden;">{svg}</div>')


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
        <span style="width:9px;height:9px;border-radius:50%;background:{GOLD2};flex:none;"></span>
        <span>bolinha = <b style="color:{TEXT};">mensagem</b></span>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ── layout principal ──────────────────────────────────────────────────────────
rede = st.session_state.rede

# ── sem anel criado ───────────────────────────────────────────────────────────
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


# ── fragmento ao vivo ─────────────────────────────────────────────────────────
@st.fragment(run_every=0.4)
def _live():
    estados = rede.estados()
    with rede.lock:
        transito = dict(rede.transito) if rede.transito else None
        logs     = list(rede.logs)

    lider       = rede.lider_atual()
    em_curso    = rede.eleicao_em_andamento
    ativos      = [e for e in estados if e["ativo"]]
    mortos      = [e for e in estados if not e["ativo"]]
    qtd_ativos  = len(ativos)
    passo_delay = next(iter(rede.nos.values())).passo_delay

    # colunas criadas dentro do fragmento
    col_ring, col_log = st.columns([1.9, 1.3])

    # ── coluna central ─────────────────────────────────────────────────────────
    with col_ring:
        # banner de fase
        tp = transito.get("tipo") if transito else None
        if em_curso and tp == "ELEICAO":
            ids_str = str(transito.get("ids", []))
            b_main  = "Fase 1 — Eleição"
            b_sub   = (f"ELEICAO de nó {transito['de']} → nó {transito['para']}. "
                       f"Ids coletados: {ids_str}.")
            bb_bdr, bb_bg, bb_mc = GOLD, "rgba(243,183,60,.07)", GOLD2
        elif em_curso and tp == "COORDENADOR":
            b_main  = "Fase 2 — Coordenador"
            b_sub   = (f"COORDENADOR de nó {transito['de']} → nó {transito['para']}, "
                       f"líder = nó {transito.get('lider')}.")
            bb_bdr, bb_bg, bb_mc = GOLD, "rgba(243,183,60,.07)", GOLD2
        elif em_curso:
            b_main  = "Eleição em andamento"
            b_sub   = "A mensagem circula pelo anel coletando ids — o maior vence."
            bb_bdr, bb_bg, bb_mc = GOLD, "rgba(243,183,60,.07)", GOLD2
        elif lider:
            b_main  = f"Estável — líder: nó {lider}"
            b_sub   = (f"Todos os {qtd_ativos} nós reconhecem o nó {lider}. "
                       f"Derrube o líder para forçar nova eleição.")
            bb_bdr, bb_bg, bb_mc = GREEN, "rgba(52,211,153,.07)", GREEN
        else:
            b_main  = "Anel pronto"
            b_sub   = "Inicie uma eleição manualmente ou use a eleição automática."
            bb_bdr, bb_bg, bb_mc = BLUE, "rgba(63,140,255,.07)", BLUE2

        st.markdown(f"""
        <div style="background:{bb_bg};border-left:3px solid {bb_bdr};
                    border-radius:4px 14px 14px 4px;padding:11px 16px;margin-bottom:12px;">
          <div style="font-weight:700;font-size:14px;color:{bb_mc};">{b_main}</div>
          <div style="font-size:12px;color:{MUTED};margin-top:3px;line-height:1.5;">{b_sub}</div>
        </div>
        """, unsafe_allow_html=True)

        # barra de ações
        ids_ativos = [e["id"] for e in ativos]
        ids_mortos = [e["id"] for e in mortos]

        ca, cb, cc = st.columns(3)
        with ca:
            with st.container(border=True):
                st.markdown(f'<div style="font-size:11.5px;font-weight:700;color:{BLUE2};">'
                            f'Iniciar eleição</div>', unsafe_allow_html=True)
                if ids_ativos:
                    ini = st.selectbox("_ini", ids_ativos,
                                       format_func=lambda x: f"Nó {x}",
                                       key="sel_ini", label_visibility="collapsed")
                    if st.button("Iniciar", use_container_width=True, key="btn_ini"):
                        rede.iniciar_eleicao_em(ini)
                else:
                    st.caption("Nenhum nó ativo.")

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

        # SVG inline do anel
        st.markdown(_svg_anel(estados, transito, passo_delay), unsafe_allow_html=True)

    # ── coluna direita: timeline ────────────────────────────────────────────────
    with col_log:
        kind_c = {
            "eleicao": GOLD, "coordenador": BLUE,
            "falha": RED, "sistema": MUTED, "info": MUTED,
        }
        rows = []
        for l in reversed(logs[-80:]):
            cor    = kind_c.get(l.get("tipo", "info"), MUTED)
            no_lbl = "sistema" if l["no"] == "sistema" else f"nó {l['no']}"
            rows.append(f"""
            <div style="background:{PANEL3};border:1px solid {BORDERS};
              border-left:3px solid {cor};border-radius:4px 9px 9px 4px;padding:7px 11px;">
              <div style="font-size:9.5px;color:{FAINT};margin-bottom:2px;
                          font-family:ui-monospace,monospace;">
                [{l['hora']}] · <span style="color:{BLUE2};">{no_lbl}</span>
              </div>
              <div style="font-size:11px;color:#cdd7ea;line-height:1.45;
                          font-family:ui-monospace,monospace;">{l['texto']}</div>
            </div>""")

        empty = (f'<div style="color:{FAINT};font-size:12px;text-align:center;padding:40px 10px;">'
                 f'Os eventos aparecerão aqui em tempo real.</div>')

        components.html(f"""<!DOCTYPE html><html><body style="margin:0;padding:13px;
          background:{PANEL};border:1px solid {BORDERS};border-radius:14px;overflow:hidden;">
          <div style="display:flex;align-items:center;justify-content:space-between;
                      margin-bottom:10px;">
            <span style="font-size:10.5px;font-weight:700;text-transform:uppercase;
                         letter-spacing:.08em;color:{MUTED};">Linha do tempo</span>
            <span style="font-size:10px;color:{FAINT};font-family:ui-monospace,monospace;">
              {len(logs)} eventos
            </span>
          </div>
          <style>
            ::-webkit-scrollbar{{width:7px}}
            ::-webkit-scrollbar-thumb{{background:#233252;border-radius:99px}}
            ::-webkit-scrollbar-track{{background:transparent}}
            body{{font-family:system-ui,sans-serif}}
          </style>
          <div style="height:calc(100vh - 60px);overflow-y:auto;
                      display:flex;flex-direction:column;gap:7px;">
            {"".join(rows) if rows else empty}
          </div>
        </body></html>""", height=700, scrolling=False)


_live()
