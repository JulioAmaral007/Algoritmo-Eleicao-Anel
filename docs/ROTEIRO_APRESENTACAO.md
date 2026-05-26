# 🎤 Roteiro de Apresentação — Algoritmo de Eleição em Anel

**Grupo 8** · Sistemas Distribuídos · UFSC — Campus Araranguá

Este roteiro foi feito para uma apresentação de **~10 a 12 minutos** com demonstração
ao vivo na interface Streamlit. Ele traz:

1. a **fala sugerida** (o que dizer em cada momento);
2. a **sequência da demonstração** (o que clicar e o que apontar na tela);
3. uma **explicação simples do algoritmo** para responder ao professor;
4. um **plano B** caso algo dê errado na hora.

> 💡 **Dica de divisão:** uma pessoa narra/explica enquanto outra opera a interface.
> Quem opera deve ensaiar os cliques pelo menos uma vez antes.

---

## ⏱️ Visão geral do tempo

| Bloco | Duração | Conteúdo |
|---|---|---|
| 1. Abertura | ~1 min | Quem somos e qual é o tema |
| 2. A ideia do anel | ~2 min | Explicação simples do algoritmo |
| 3. Arquitetura | ~2 min | Como os nós conversam (sockets) |
| 4. **Demonstração** | ~4 min | Eleição, falha do líder e nova eleição |
| 5. Análise | ~1,5 min | Vantagens, desvantagens, complexidade |
| 6. Fechamento | ~0,5 min | Conclusão e perguntas |

---

## 1. Abertura (~1 min)

> "Bom dia/boa tarde. Somos o **Grupo 8** e o nosso tema é o **Algoritmo de Eleição
> em Anel**.
>
> Em um sistema distribuído, vários processos rodam ao mesmo tempo, e muitas vezes
> precisamos que **um deles** assuma um papel especial — o **coordenador** ou **líder**.
> O problema é: como vários processos, sem um chefe central, conseguem **concordar**
> sobre quem é o líder? E o que acontece quando esse líder **falha**?
>
> É exatamente isso que o algoritmo de eleição em anel resolve, e nós o implementamos
> em Python com **sockets reais** e uma **interface visual** para mostrar tudo
> acontecendo em tempo real."

**Apontar na tela:** o título da aplicação Streamlit já aberta.

---

## 2. A ideia do anel — explicação simples (~2 min)

> "A ideia é organizar os processos em um **anel lógico**: cada nó conhece apenas o
> **próximo** (o sucessor). O nó 1 fala com o 2, o 2 com o 3, e o último volta para o 1,
> fechando o círculo.
>
> Cada nó tem um **número de identificação (id)**. A regra de quem ganha a eleição é
> bem simples e combinada por todos: **vence o nó de maior id**.
>
> Quando alguém percebe que não há líder (por exemplo, no início, ou porque o líder
> caiu), ele **começa uma eleição**:
>
> 1. cria uma mensagem de **ELEIÇÃO** e coloca o próprio id nela;
> 2. envia para o sucessor;
> 3. cada nó que recebe **acrescenta o próprio id** à lista e repassa adiante;
> 4. quando a mensagem **dá a volta completa** e retorna a quem já está na lista,
>    todos os candidatos vivos já foram coletados;
> 5. pega-se o **maior id** da lista → esse é o novo líder;
> 6. uma segunda mensagem, a de **COORDENADOR**, circula anunciando o vencedor para
>    que **todos atualizem** quem é o líder."

**Analogia para a turma (opcional, fica ótimo):**

> "É como passar uma folha de papel em roda: cada pessoa escreve o próprio número e
> passa para o lado. Quando a folha completa a volta, todos olham e o maior número
> ganha. Depois passamos um segundo bilhete dizendo 'o fulano é o líder' para todo
> mundo ficar sabendo."

---

## 3. Arquitetura — como os nós conversam (~2 min)

> "Cada nó é, ao mesmo tempo, um **servidor** (tem uma thread escutando em uma porta
> TCP) e um **cliente** (abre conexões para mandar mensagens ao sucessor). As mensagens
> são objetos **JSON** simples, com um campo `tipo` (ELEICAO, COORDENADOR, PING…) e os
> dados.
>
> Além disso, cada nó tem uma **thread monitora** que fica perguntando ao líder, de
> tempos em tempos, 'você está vivo?' com um **PING**. Se o líder não responde com
> **PONG**, o nó conclui que o líder caiu e **dispara uma nova eleição sozinho** — sem
> ninguém mandar."

**Apontar na tela / no relatório:** o diagrama da arquitetura e o de sequência que
estão no `RELATORIO.md` (seções 3 e 5), se estiver projetando o documento.

Frase-chave para o professor:

> "Não é uma simulação 'de mentirinha': são **conexões TCP reais** em `localhost`.
> A detecção de falha acontece porque a conexão é **recusada** quando o processo do
> nó não está mais escutando."

---

## 4. Demonstração ao vivo (~4 min) — o coração da apresentação

> ⚙️ **Antes de apresentar:** já deixe rodando `streamlit run app.py` e o navegador
> aberto na página. Assim você não perde tempo.

### Passo 4.1 — Criar o anel

- Na **barra lateral**, deixe **5 nós** e um **delay** de ~0,6 s (o delay deixa as
  mensagens lentas o suficiente para a turma enxergar cada passo).
- Mantenha marcada a opção de **eleição inicial automática**.
- Clique em **“Criar anel / Reiniciar”**.

> "Acabei de criar 5 nós, do id 1 ao 5. Como pedi a eleição inicial, eles já estão
> elegendo um líder agora. Reparem nas mensagens de **ELEIÇÃO** circulando…"

**Apontar:** a bolinha animada percorrendo as arestas do anel e os **logs** descendo.

> "...e pronto: o nó **5**, que tem o maior id, foi eleito **líder** — está destacado
> em dourado com a coroa 👑."

### Passo 4.2 — Derrubar o líder (simular falha)

- Na seção de ações, escolha o **nó líder (5)** e clique em **“Derrubar nó”**.

> "Agora vou simular uma **falha do líder**: derrubei o nó 5. Ele aparece em vermelho,
> tracejado, marcado como inativo. Nenhum de nós mandou iniciar eleição…"

**Apontar:** o nó 5 ficando vermelho/✖ e, em seguida, **novas mensagens de ELEIÇÃO**
surgindo nos logs **sozinhas**.

> "...mas a thread monitora dos outros nós percebeu que o líder parou de responder ao
> PING e **disparou automaticamente** uma nova eleição. Vejam o novo líder sendo
> escolhido: agora é o nó **4**, o maior id **entre os que continuam vivos**."

### Passo 4.3 — Reviver o nó e nova eleição manual

- Selecione o **nó 5** e clique em **“Reviver nó”**.
- Em seguida clique em **“Iniciar eleição”** (em qualquer nó).

> "O nó 5 voltou ao ar. Note que ele **não vira líder automaticamente** só por ter
> voltado — o líder atual continua sendo o 4. Mas se eu disparar uma **nova eleição
> manual**, o 5 volta a ganhar, porque tem o maior id. É assim que o sistema sempre
> converge para um líder bem definido."

**Apontar:** a coroa voltando para o nó 5 e o log da mensagem de COORDENADOR confirmando.

### Passo 4.4 (opcional, se sobrar tempo) — Derrubar um nó comum

> "Posso ainda derrubar um nó que **não é** o líder. Reparem que **nada acontece** com
> a liderança: o anel só repassa as mensagens pulando o nó morto. A eleição só é
> necessária quando quem cai é o **líder**."

---

## 5. Análise (~1,5 min)

> "Por que escolher o anel?
>
> - **Vantagem:** é **simples** e **organizado** — cada nó só precisa conhecer o
>   sucessor, e o número de mensagens é **linear**, da ordem de **2·n** (uma volta para
>   eleger, outra para anunciar). É bem mais econômico que o algoritmo do Valentão
>   (*Bully*), que pode chegar a **n²** mensagens.
> - **Desvantagem:** depende da estrutura do anel; se um nó cai, é preciso saber
>   **pular** para o próximo nó vivo, que foi justamente o que tratamos no código com a
>   função que repassa para o **sucessor vivo**.
>
> E como evitamos conflito de dois líderes? A regra do **maior id** é **determinística**:
> não importa quem começou a eleição, a lista coletada é a mesma e o `max` dos ids dá
> sempre o **mesmo** resultado. Por isso todos concordam."

---

## 6. Fechamento (~0,5 min)

> "Resumindo: implementamos o algoritmo de eleição em anel com comunicação real por
> sockets, detecção automática de falha do líder, reeleição automática e uma interface
> que deixa todo o processo visível. O código está organizado em módulos pequenos e
> comentados, e o relatório no GitHub detalha a arquitetura, a comunicação e os testes.
>
> Obrigado! Estamos abertos a perguntas."

---

## ❓ Perguntas prováveis do professor (e respostas curtas)

**“Como vocês identificam os processos?”**
> Cada nó recebe um **id inteiro** e um endereço `host:porta`. O anel é uma lista
> ordenada desses ids; a posição na lista define o sucessor de cada um.

**“Como uma mensagem é enviada e recebida, na prática?”**
> Abrimos um **socket TCP** para o `host:porta` do sucessor e enviamos um **JSON
> terminado por `\n`**. Do outro lado, a thread servidora lê a linha, decodifica o JSON
> e decide a ação pelo campo `tipo`. (Mostrar seções 7.1 e 7.2 do relatório.)

**“Como detectam que o líder caiu?”**
> Uma **thread monitora** envia **PING** ao líder periodicamente. Sem **PONG** (conexão
> recusada/timeout), o nó assume falha e chama `iniciar_eleicao`.

**“E se dois nós iniciarem a eleição ao mesmo tempo?”**
> Tudo bem: as duas mensagens coletam a mesma lista de ids vivos e o **maior id** vence
> em ambas. Usamos um sinalizador `eleicao_em_andamento` para não duplicar trabalho à toa.

**“Por que o maior id, e não o menor?”**
> É uma **convenção**. O essencial é que a regra seja **determinística** e conhecida por
> todos. Poderia ser o menor — bastaria trocar `max` por `min`.

**“Qual a complexidade?”**
> **O(n)** em mensagens por eleição — aproximadamente **2·n** (volta da eleição + volta
> do anúncio do coordenador).

---

## 🛟 Plano B (se algo travar na hora)

- **A interface não atualiza:** clique em **“Criar anel / Reiniciar”** de novo; o
  estado é recriado do zero.
- **Streamlit não abre:** rode no terminal `streamlit run app.py` e use a URL
  `http://localhost:8501`.
- **Quer mostrar que são sockets de verdade:** abra 3 terminais e rode a **Opção 2** do
  README (`server.py` em cada um + `client.py` para comandar). É o argumento mais forte
  para o professor de que a comunicação é real.
- **Travou tudo:** tenha a pasta `docs/img/` aberta — as imagens
  `01_anel_eleito.png`, `02_lider_caiu.png` e `03_novo_lider.png` contam a história
  inteira mesmo sem a interface ao vivo.

---

## ✅ Checklist rápido (antes de começar)

- [ ] `pip install -r requirements.txt` já executado
- [ ] `streamlit run app.py` rodando e navegador aberto
- [ ] anel de teste criado uma vez para conferir que funciona
- [ ] relatório (`RELATORIO.md`) aberto em outra aba, caso queira mostrar diagramas
- [ ] combinado quem fala e quem opera a interface
