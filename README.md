# Algoritmo de Eleição em Anel

Implementação didática e visual do algoritmo clássico de eleição de líder em anel, com nós reais comunicando-se via sockets TCP e interface animada em tempo real.

---

## 🚀 Visão Geral

Em sistemas distribuídos sem um coordenador central, os processos precisam **eleger um líder** para coordenar tarefas compartilhadas. Quando esse líder falha, o sistema deve eleger um substituto automaticamente — sem intervenção humana e sem conflitos.

Este projeto implementa o **Algoritmo de Eleição em Anel**: os nós formam um anel lógico e trocam mensagens TCP reais para eleger o nó de maior identificador como líder. A implementação inclui detecção automática de falha e reeleição, com uma interface visual que anima cada salto de mensagem pelo anel em tempo real.

**Público-alvo:** estudantes e professores de Sistemas Distribuídos que queiram ver o algoritmo funcionando de forma concreta — não apenas simulado, mas com processos e sockets reais.

---

## 🛠️ Tecnologias Utilizadas

- **Linguagem:** Python 3.12
- **Interface visual:** Streamlit ≥ 1.37
- **Comunicação:** Sockets TCP (biblioteca padrão — `socket`, `threading`)
- **Protocolo de mensagens:** JSON delimitado por `\n` (biblioteca padrão — `json`)
- **Concorrência:** `threading` (uma thread de servidor + uma de monitor por nó)

Não há banco de dados, autenticação ou dependências externas além do Streamlit.

---

## 🎯 Principais Funcionalidades

- **Eleição de líder em duas voltas**: mensagem `ELEIÇÃO` circula coletando os IDs dos nós vivos; o maior ID vence. Em seguida, mensagem `COORDENADOR` circula avisando todos do resultado.
- **Detecção automática de falha**: cada nó monitora o **seu sucessor** com PING/PONG a cada 1,5 s (modelo puro — só conhece o próximo nó). Se o sucessor cair, o anel se reconfigura; se o nó que caiu era o líder, uma nova eleição é disparada automaticamente.
- **Tolerância a falhas parciais**: ao enviar uma mensagem, o nó pula sucessores mortos e continua pelo próximo vivo — o algoritmo funciona mesmo com vários nós caídos simultaneamente.
- **Interface visual animada**: anel SVG que destaca a seta dourada na aresta por onde a mensagem está passando; seta tracejada quando há um salto sobre nó morto.
- **Linha do tempo em tempo real**: painel lateral com todos os eventos (eleição, coordenador, falha, sistema) coloridos por tipo.
- **Modo multi-processo real**: cada nó pode rodar como um processo independente em terminais separados, comunicando-se de verdade pela rede local.
- **Cliente de linha de comando**: envia comandos (`eleicao`, `status`, `ping`) a qualquer nó por socket.
- **Teste automatizado**: script que cobre os três cenários — eleição inicial, falha do líder e reeleição após retorno do nó.

---

## 🏗️ Arquitetura

O projeto é organizado em camadas, cada uma com uma responsabilidade clara:

```
utils.py  ──►  election.py  ──►  node.py  ──►  app.py
                                           ──►  server.py / client.py
```

**Protocolo de rede (`utils.py`):** toda comunicação usa JSON terminado em `\n` sobre TCP. Uma conexão = uma mensagem. Retorno `None` de `enviar_mensagem()` é o mecanismo de detecção de falha — conexão recusada significa nó morto.

**Algoritmo puro (`election.py`):** sem código de rede ou de interface. Recebe um objeto `no` e executa as três funções do protocolo: `iniciar_eleicao`, `processar_eleicao` e `processar_coordenador`.

**Nó e rede (`node.py`):** a classe `Node` é ao mesmo tempo servidor (thread que aceita conexões) e monitor (thread que faz PING no **seu sucessor** — modelo puro: o nó só conhece o próximo nó vivo). A classe `Rede` cria e gerencia N nós e atua como **serviço de topologia/membership** (responde `proximo_vivo`), mantendo o log compartilhado e o dicionário de mensagens em trânsito (`transitos`) usado pela interface.

**Interface visual (`app.py`):** Streamlit com `@st.fragment(run_every=0.25s)` atualizando o SVG do anel e a linha do tempo. O SVG é renderizado inline (não em iframe) para atualização por diff do DOM, sem flashes.

**Modo distribuído (`server.py` / `client.py`):** `server.py` instancia um único `Node` por processo usando `_TopologiaProcesso` (serviço de topologia mínimo que descobre o sucessor vivo por PING, já que processos separados não compartilham memória). `client.py` envia comandos por socket TCP.

---

## 📂 Estrutura do Projeto

```
algoritmo/
├── utils.py              # Protocolo de rede: envio, recebimento e tipos de mensagem
├── election.py           # Algoritmo de eleição (lógica pura, sem I/O)
├── node.py               # Classe Node (servidor + monitor) e Rede (gerenciador)
├── app.py                # Interface visual Streamlit
├── server.py             # Executa um nó como processo independente
├── client.py             # Cliente de linha de comando
├── teste_eleicao.py      # Teste automatizado dos 3 cenários
├── requirements.txt      # Dependência: streamlit>=1.37
└── docs/
    ├── RELATORIO.md              # Relatório completo do trabalho
    ├── ROTEIRO_APRESENTACAO.md   # Roteiro de fala para a apresentação
    └── img/                      # Capturas de tela
```

---

## ⚙️ Como Executar

### Pré-requisitos

- Python 3.10 ou superior
- pip

### Instalação

```bash
git clone <url-do-repositorio>
cd algoritmo
pip install -r requirements.txt
```

### Opção 1 — Interface visual (recomendada)

```bash
streamlit run app.py
```

Abre no navegador automaticamente. Na barra lateral:

1. Ajuste a quantidade de nós e o atraso por salto.
2. Clique em **Criar anel / Reiniciar** — a eleição inicial acontece automaticamente.
3. Use **Derrubar um nó** no líder para simular falha e observe a nova eleição.
4. Use **Reviver um nó** e **Iniciar eleição** para explorar outros cenários.

### Opção 2 — Processos distribuídos reais

Abra um terminal por nó:

```bash
python server.py --id 1 --anel 1:5001,2:5002,3:5003
python server.py --id 2 --anel 1:5001,2:5002,3:5003
python server.py --id 3 --anel 1:5001,2:5002,3:5003
```

Em outro terminal, comande os nós:

```bash
python client.py --porta 5001 --comando eleicao   # inicia eleição
python client.py --porta 5002 --comando status    # consulta estado
python client.py --porta 5003 --comando ping      # verifica se está vivo
```

Pressione **Ctrl+C** no terminal do líder para simular sua queda — os demais detectam e elegem novo líder automaticamente.

### Teste automatizado

```bash
python teste_eleicao.py
```

Cobre três cenários com asserts: eleição inicial (maior ID vence), falha do líder (detecção + reeleição automática) e retorno do nó (reeleição manual).

---

## 📡 Protocolo de Mensagens

Cada mensagem é um dicionário Python serializado como JSON, terminado em `\n`, enviado sobre TCP. Uma conexão TCP transporta exatamente uma mensagem.

| Tipo | Direção | Descrição |
|---|---|---|
| `ELEICAO` | nó → sucessor | Coleta IDs dos nós vivos (lista cresce a cada salto) |
| `COORDENADOR` | nó → sucessor | Anuncia o novo líder após a volta completa |
| `PING` | monitor → sucessor | Verifica se o sucessor está vivo |
| `PONG` | sucessor → monitor | Confirma que está vivo |
| `STATUS` | client → nó | Solicita snapshot do estado do nó |
| `INICIAR_ELEICAO` | client → nó | Pede ao nó que dispare uma eleição |

---

## 🔁 Fluxo da Eleição

```
Volta 1 — ELEIÇÃO (coleta de candidatos)
  Nó iniciador  ──[ids: {1}]──►  Nó 2  ──[ids: {1,2}]──►  Nó 3
  ◄──[ids: {1,2,3}]──  Nó 3 repassa de volta ao Nó 1
  Nó 1 vê seu próprio id na lista → vence o MAIOR id → inicia Volta 2

Volta 2 — COORDENADOR (anúncio)
  Nó 1  ──[lider: 3]──►  Nó 2  ──[lider: 3]──►  Nó 3
  ◄──[lider: 3]──  anúncio retorna ao Nó 1 → eleição encerrada
```

Se o sucessor imediato estiver morto, a mensagem pula para o próximo vivo. Se nenhum outro nó responder, o nó se declara líder sozinho.

---

## 📈 Possíveis Melhorias

- Suporte a nós em hosts diferentes (hoje todos usam `127.0.0.1`)
- Persistência do estado em arquivo para recuperação após reinício completo
- Interface de linha de comando interativa (modo REPL)
- Métricas de latência por salto exibidas na interface

---

## 👨‍💻 Desenvolvedores

Desenvolvido pelo **Grupo 8** — UFSC Campus Araranguá.

---

## 📚 Contexto Acadêmico

Trabalho prático da disciplina de **Sistemas Distribuídos** — Universidade Federal de Santa Catarina, Campus Araranguá. O tema sorteado para o Grupo 8 foi o **Algoritmo de Eleição — Algoritmo de Anel**.

O relatório completo com diagramas de sequência, análise de complexidade e comparação com outros algoritmos de eleição está em [`docs/RELATORIO.md`](docs/RELATORIO.md).
