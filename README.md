# 🔵 Algoritmo de Eleição em Anel — Grupo 8

**Disciplina:** Sistemas Distribuídos · **UFSC — Campus Araranguá**
**Tema (Grupo 8):** Algoritmo de Eleição — Algoritmo de Anel

Implementação **didática** do algoritmo de eleição de líder em anel, com:

- 🧩 nós reais que se comunicam por **sockets TCP** (cliente/servidor);
- 👑 **eleição** do líder, **detecção de falha** e **nova eleição automática**;
- 🎬 uma **interface visual em Streamlit** que mostra o anel, o líder e as
  mensagens circulando em tempo real.

![Anel com líder eleito](docs/img/01_anel_eleito.png)

---

## 🚀 Como executar

### Opção 1 — Interface visual (recomendada para a apresentação)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Depois, no navegador:
1. clique em **Criar anel / Reiniciar** (barra lateral);
2. observe a **eleição inicial** acontecer (o nó de maior id vira líder 👑);
3. use **Derrubar nó** no líder para simular uma falha → veja a **nova eleição**;
4. use **Reviver nó** e **Iniciar eleição** para explorar outros cenários.

### Opção 2 — Sistema realmente distribuído (vários processos)

Abra um terminal para cada nó:

```bash
python3 server.py --id 1 --anel 1:5001,2:5002,3:5003
python3 server.py --id 2 --anel 1:5001,2:5002,3:5003
python3 server.py --id 3 --anel 1:5001,2:5002,3:5003
```

Em outro terminal, use o **cliente** para comandar os nós:

```bash
python3 client.py --porta 5001 --comando eleicao   # inicia a eleição
python3 client.py --porta 5002 --comando status    # consulta o estado de um nó
python3 client.py --porta 5003 --comando ping      # verifica se um nó está vivo
```

Para simular a queda do líder, pressione **Ctrl+C** no terminal dele — os outros
detectam e iniciam uma nova eleição sozinhos.

---

## 📁 Estrutura do projeto

| Arquivo | O que faz |
|---|---|
| `utils.py` | Funções de baixo nível: envio/recebimento de mensagens por socket. |
| `election.py` | **O algoritmo de eleição em anel** (a "receita", bem comentada). |
| `node.py` | O **nó** (servidor + cliente + detector de falha) e a **Rede** que os gerencia. |
| `server.py` | Roda **um nó como processo** independente (demo multi-terminal). |
| `client.py` | **Cliente** de linha de comando para enviar comandos a um nó. |
| `app.py` | **Interface visual** em Streamlit. |
| `teste_eleicao.py` | **Teste automatizado** dos 3 cenários (eleição, falha, reeleição). |
| `docs/RELATORIO.md` | Relatório completo (arquitetura, sockets, diagramas, testes). |
| `docs/ROTEIRO_APRESENTACAO.md` | Roteiro de fala e sequência da demonstração. |

---

## 📖 Em uma frase

> Os nós formam um **anel**. Quando o líder cai, alguém inicia uma **eleição**:
> uma mensagem dá a volta no anel **coletando os ids** dos nós vivos; vence o
> **maior id**; então um anúncio de **coordenador** circula avisando todos.

Leia o passo a passo completo em [`docs/RELATORIO.md`](docs/RELATORIO.md).
