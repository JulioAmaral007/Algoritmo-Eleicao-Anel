# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Didactic implementation of the **ring election algorithm** (leader election in distributed systems) for a Distributed Systems course at UFSC (Grupo 8). Nodes are real TCP socket servers/clients; a Streamlit UI animates the ring. Code, comments, logs, and docs are all in **Portuguese** — keep new code/comments in Portuguese to match.

## Commands

```bash
pip install -r requirements.txt   # only dependency is streamlit

# Run the visual demo (recommended)
streamlit run app.py

# Run the automated test (the only test; plain script with asserts, no pytest)
python teste_eleicao.py

# Run as truly distributed processes (one terminal per node)
python server.py --id 1 --anel 1:5001,2:5002,3:5003
python server.py --id 2 --anel 1:5001,2:5002,3:5003
python server.py --id 3 --anel 1:5001,2:5002,3:5003

# Command a running node from another terminal
python client.py --porta 5001 --comando eleicao|status|ping
```

## Architecture

Layered by concern — keep the separation when editing:

- **`utils.py`** — wire protocol and ALL socket I/O. Messages are JSON dicts terminated by `\n`; one TCP connection = one message. Message type constants (`MSG_ELECTION`, `MSG_COORDINATOR`, `MSG_PING`, `MSG_PONG`, `MSG_STATUS`, `MSG_INICIAR_ELEICAO`) live here. `enviar_mensagem()` returns `None` on any connection failure — that return value IS the failure-detection mechanism.
- **`election.py`** — the pure algorithm, no socket/UI code. Two passes: an ELEICAO message circulates collecting live node ids (round closes when a node sees its own id already in the list; highest id wins), then a COORDENADOR announcement circulates. `_enviar_para_sucessor_vivo()` skips dead successors and self-declares leader if the node is alone.
- **`node.py`** — `Node` (server thread accepting connections + monitor thread that pings the leader every 1.5s and triggers re-election on failure) and `Rede` (creates N nodes, holds the shared `logs`/`transitos`/`lock` used by the UI; `transitos` is a dict keyed by sender id so concurrent in-flight messages don't clobber each other). `derrubar()` simulates failure by closing the listening socket; staggered monitor start delays (`0.15 * id`) avoid simultaneous elections.
- **`server.py` / `client.py`** — run one `Node` per process / send commands to a node. `server.py` uses `_RedeShim`, a minimal stand-in for `Rede` (lock, logs, transitos, eleicao_em_andamento) — if you add attributes Node reads from `rede`, update the shim too.
- **`app.py`** — Streamlit UI driving a `Rede` stored in `st.session_state`; renders the ring as SVG from `rede.estados()` and the shared `transito` state set by `Node.marcar_transito()`.

## Platform constraints (Windows)

- `SO_REUSEADDR` is deliberately **not** set on Windows (it would allow double-bind there). Instead, `app.py` advances the port base by 100 on every ring recreation to get fresh ports. Sockets are bound in `Node.iniciar()` (not inside the server thread) so bind failures surface immediately — don't move the bind.
- Scripts call `sys.stdout.reconfigure(encoding="utf-8")` because logs contain emojis and the Windows console defaults to cp1252.

## Demo pacing

`passo_delay` (default 0.6s per hop) is an intentional artificial delay so the animation is visible; the test uses 0.05 and relies on `time.sleep()` windows for elections to finish. If you change timing (monitor interval, delays), revisit the sleeps in `teste_eleicao.py`.
