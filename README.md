# Turista Viajante

Você marca os lugares que quer visitar numa cidade e o app devolve **a ordem que gasta menos tempo andando**,
saindo e voltando ao hotel, respeitando o horário de funcionamento de cada lugar. Se não couber no dia, ele diz
exatamente por quê.

Projeto de portfólio que junta três coisas: **dados extraídos com LLM**, **Pesquisa Operacional** (CP-SAT) e um
front de mapa. Nasceu de uma dor real: montar o roteiro de uma viagem e decidir "vou primeiro no X ou no Y?".

| Cidade | Situação |
|---|---|
| Florianópolis | pronta: 137 lugares (sem restaurantes) |
| Montreal | em andamento: cobertura parcial, ainda classificando |
| Genebra | configurada, ainda sem dados (fora da interface por enquanto) |

## Como usar

Com o app aberto (veja [Começando](#começando)):

1. **Partida.** O navegador pergunta se pode usar sua localização como ponto de partida (o hotel). É opcional: se
   você negar, ou estiver a mais de 60 km da cidade, o app usa o centro dela. Em qualquer caso dá para **arrastar o
   marcador laranja (H)** no mapa, ou clicar em "Usar minha localização" para tentar de novo.
2. **Cidade.** Escolha no topo; só aparecem as cidades que já têm dados, e "parcial" avisa que a lista ainda não
   cobre tudo.
3. **Dia.** Data, hora de saída, hora limite de volta e como você se desloca (**a pé** ou **de carro**).
4. **Lugares.** Na aba *Lugares*, filtre por região, tag ("autêntico", "natureza", "cartão-postal"...) ou nome, e
   **marque** os que quer visitar, na lista ou clicando nos pontos do mapa. O medidor embaixo mostra quanto das horas
   do dia só as visitas já ocupam (sem contar o deslocamento).
5. **Montar roteiro.** Abre um pop-up com a **hora de chegada em cada lugar**, o tempo de deslocamento entre eles,
   as esperas (quando o lugar ainda não abriu) e a hora de volta ao hotel.
6. **Usar o roteiro.** *Ver no mapa* mostra a rota numerada; *Copiar como texto* leva o plano para uma mensagem;
   *Abrir no Google Maps* abre a rota hotel → paradas → hotel (acima de 9 paradas, o Google Maps limita, então o
   botão se divide em partes encadeadas).

**"Não cabe no dia".** Significa que não existe ordem que respeite os horários e a janela do dia. A mensagem diz
por quê (por exemplo: "as visitas somam 300 min e o menor deslocamento possível é 247 min, mais que a janela de
540 min"); tire um lugar, alargue o horário ou troque o dia.

**Bom saber.** Lugar sem horário no Google é tratado como sempre aberto. Os tempos de deslocamento são
estimativas do OSRM e podem diferir dos do Google Maps. O botão com a lua/sol alterna o tema claro/escuro.

## Como funciona

```
  OFFLINE (pipeline/)                                          ONLINE
  ┌──────────────────────────────────────────┐        ┌─────────────────────────────────┐
  │ agente de descoberta (LangGraph)         │        │ React + Vite + MapLibre         │
  │   decide as buscas no Google Places      │        │   marca lugares, mostra rota    │
  │ detalhes + reviews                       │        └───────────────┬─────────────────┘
  │ classificação por LLM (features/lugar)   │                        │ POST /api/cities/{id}/route
  │ merge  ──► places.json                   │        ┌───────────────▼─────────────────┐
  │ matriz de tempos (OSRM) ──► matrix_*.json│ ─dados─►│ FastAPI                         │
  └──────────────────────────────────────────┘        │   linha do hotel ao vivo (OSRM)  │
                                                      │   solver CP-SAT (TSP + janelas)  │
                                                      └─────────────────────────────────┘
```

1. **Descoberta.** Um agente (LangGraph) decide *quais* buscas fazer no Google Places para cobrir cada região e
   tipo de lugar, incluindo a "cauda longa" pouco turística que a busca por popularidade esconde. O LLM propõe; o
   código impõe orçamento de chamadas, deduplicação e mínimos por tipo.
2. **Classificação.** Um LLM aberto (gpt-oss, via Groq) lê as reviews e extrai, por lugar: categoria, se é refeição,
   se é pago, duração típica e notas de 0 a 1 (autenticidade, turistão, cultura, natureza, marco). Saída validada por
   schema (Pydantic), com repetição quando o JSON vem inválido.
3. **Distâncias.** Matriz de tempos a pé e de carro por cidade (OSRM), calculada uma vez. A linha do hotel é
   calculada ao vivo, porque o hotel muda a cada viagem (pode vir da geolocalização do navegador).
4. **Solver.** Ordena o dia inteiro em CP-SAT.

## O problema de otimização

Um dia, um hotel (nó 0), lugares marcados `P` (todos obrigatórios). Para cada lugar `i`: duração de visita `s_i` e
janelas de abertura do dia da semana. Com `x_ij ∈ {0,1}` (vou de `i` para `j`), `t_i` a hora de chegada e `c_ij` o
tempo de deslocamento:

```
min  2048 · Σ c_ij · x_ij  +  t_volta
s.a. x forma um único circuito hamiltoniano por hotel ∪ P            (AddCircuit)
     x_ij = 1  ⇒  t_j ≥ t_i + s_i + c_ij                              (espera é permitida)
     t_i ∈ ⋃_k [abre_ik , fecha_ik − s_i]                             (horário não convexo = domínio)
     t_início ≤ t_i ,  t_volta ≤ t_fim
```

<p align="center"><img src="docs/formulacao.png" alt="Formulação matemática do modelo" width="520"></p>

- **Lexicográfico em uma resolução:** o peso 2048 > 1440 min/dia faz o deslocamento ter prioridade estrita; em
  empate, vence quem volta ao hotel mais cedo.
- **`AddCircuit` em vez de MTZ:** elimina subciclos sem restrições extras, e cada condição vira `OnlyEnforceIf`
  (implicação exata, sem *big-M*). Horário partido ("9h–12h e 14h–18h") entra como domínio, o que é nativo em CP.
- **Matriz com fecho métrico** (Floyd–Warshall): garante desigualdade triangular.
- **Inviável com explicação.** Quando não cabe, o solver não devolve só "INFEASIBLE": checa causas óbvias (lugar
  fechado naquele dia), depois um certificado (*soma das visitas + menor deslocamento possível > janela do dia*,
  onde o menor deslocamento é um TSP puro, fácil de resolver) e, por fim, o **menor subconjunto de lugares em conflito**
  por filtro de remoção.

### Uma versão maior que ficou guardada (v2)

A primeira ideia era o solver **escolher** os lugares (orienteering multi-dia com estilos como "Primeira vez" ou
"Como um local"). Esse código continua no repositório (`solver/model.py`, `benders.py`, `scoring.py`), fora do
caminho da v1, e a comparação foi instrutiva: em 3 dias com 5 lugares por dia, o modelo monolítico não provava o
ótimo nem em 30 s, enquanto uma **decomposição de Benders lógica** (mestre escolhe quais lugares vão em qual dia;
subproblema resolve a rota de cada dia ao ótimo) provou em ~1 s.

| Candidatos | CP-SAT monolítico (30 s) | Decomposição de Benders |
|---|---|---|
| 16 | 130 min, gap 18% | **130 min, ótimo, 0,6 s** |
| 30 | 93 min, gap 18% | **93 min, ótimo, 1,2 s** |
| 45 | 77 min, gap 18% | **76 min, ótimo, 1,4 s** |

O ganho veio de cortes sobre **subconjuntos** (por monotonia: se `T ⊇ S`, `custo(T) ≥ custo(S)`): cortes só do
conjunto exato deixavam o mestre aprendendo devagar (gap de 60% a 80% em 30 s). Foi validado contra força bruta em
dezenas de instâncias. Dados aleatórios, sem horários reais; com os de Florianópolis o ótimo levou ~15 s.

## Decisões e limites

- **Dados do Google Places** (API oficial), não scraping. As reviews vêm no máximo 5 por lugar, e ~80% são de 5
  estrelas, então o texto diz pouco sobre autenticidade; o classificador usa também nota, nº de avaliações e tipos.
- **Só pedimos ao Google o que usamos.** Das reviews vêm apenas nota e texto: o campo `reviews` inteiro traria também
  nome, foto e perfil de cada autor, que o projeto não usa e não guarda.
- **Mapa-base do OpenFreeMap** (vetorial, dados do OpenStreetMap, sem chave de API; estilos claro e escuro). Os tiles
  da CARTO foram testados e passaram a exigir chave.
- **Restaurantes ficam fora** da lista (decisão de produto: o objetivo é rotear visitas).
- **OSRM público** para as distâncias: gratuito, com perfil a pé e de carro. É um serviço compartilhado de uso
  justo e sem garantia; serve a esta fase, mas o caminho de produção é hospedar um OSRM próprio. Os tempos dele
  ficaram ~12% maiores que os do OpenRouteService em 6 pares de Montreal (mais conservadores). Se o serviço cair, o
  app aproxima o hotel pelo lugar mais próximo e avisa. O ORS continua como provedor alternativo (`ROUTING_PROVIDER=ors`).
- **Sem horário no Google = sempre aberto.**
- **Termos do Google.** O repositório publica só dados derivados (`places.json`: nome, coordenadas, horários,
  features do LLM; e as matrizes). Os detalhes brutos e as reviews não são distribuídos; quem clonar reconstrói
  com as próprias chaves.
- **Classificação sem gabarito humano.** Não há avaliação de acurácia das features do LLM (um juiz com modelo maior
  estava planejado e não foi feito).

## Começando

**O que você precisa ter:** Python 3.12 e Node 20 ou mais novo. **Não precisa de nenhuma chave de API** para usar o
app com as cidades que já estão no repositório.

```bash
# 1. ambiente Python
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt      # Windows; Linux/macOS: .venv/bin/python

# 2. front-end (gera web/dist, que a API serve)
cd web && npm install && npm run build && cd ..

# 3. rodar
.venv/Scripts/python -m uvicorn api.main:app --port 8000
```

Abra **http://127.0.0.1:8000**. Para conferir que está tudo certo: `.venv/Scripts/python -m pytest tests -q` e
`cd web && npm test` (nenhum usa rede).

**Se algo não aparecer**
- *A página abre em branco ou dá `{"detail":"Not Found"}`:* faltou o passo 2 (`npm run build`); a API só serve o
  front se `web/dist` existir.
- *Mudei o Python e nada mudou:* o servidor não recarrega sozinho; reinicie o `uvicorn`.
- *A cidade não aparece na lista:* ela precisa de `places.json` **e** das matrizes `matrix_walk.json`/`matrix_car.json`
  em `data/cities/<cidade>/`.
- *O mapa mostra só o fundo, sem pontos:* o front foi construído sem o worker do MapLibre; use `npm run build` do
  repositório (o import do worker está em `web/src/MapView.tsx`).

Para desenvolver o front com recarga automática: `cd web && npm run dev` (proxy de `/api` para a porta 8000).

## Criar ou atualizar uma cidade

Precisa de chaves no `.env` (o script `scripts/setup_keys.sh` guia a criação): `GOOGLE_PLACES_API_KEY` e
`GROQ_API_KEY`. Crie `data/cities/<id>/city.json` (regiões, caixa geográfica, idioma) e rode:

```bash
.venv/Scripts/python scripts/build_city.py <id>          # descoberta → detalhes → classificação → merge
.venv/Scripts/python scripts/refresh_matrices.py <id>    # matrizes a pé e de carro
```

Tudo é retomável. O plano grátis da Groq limita a ~200 mil tokens por dia por modelo, então uma cidade grande pode
levar mais de um dia; o Google tem um livro-caixa local (`data/ledger.json`) que bloqueia chamadas acima de 800 por mês.

### Deploy

Há um `Dockerfile` para Hugging Face Spaces (porta 7860), **ainda não testado**: não havia Docker na máquina de
desenvolvimento. A imagem leva só `places.json`, `city.json`, `coverage.json` e as matrizes.

## Estrutura

```
pipeline/   coleta e estruturação dos dados (agente, Places, classificação, merge, matrizes)
solver/     tsp.py (v1) · model.py, benders.py, scoring.py (v2, guardados)
api/        FastAPI: lista de lugares e roteiro
web/        React + Vite + MapLibre
scripts/    pipeline por cidade, matrizes, wizard de chaves
data/       dados derivados por cidade
tests/      Python (solver contra força bruta, pipeline com respostas simuladas, API)
```

Detalhes para quem desenvolve (comandos, armadilhas): [CLAUDE.md](CLAUDE.md).
