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
| Genebra | configurada, sem dados ainda |

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

## Rodando

Requisitos: Python 3.12, Node 20+.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt      # Windows; em Linux/macOS: .venv/bin/python
cd web && npm install && npm run build && cd ..
.venv/Scripts/python -m uvicorn api.main:app --port 8000          # abre http://127.0.0.1:8000
```

O app já funciona com os dados de `data/cities/` do repositório; **não precisa de chaves** para usar. Para
desenvolver o front: `cd web && npm run dev` (proxy de `/api` para a porta 8000).

**Testes:** `.venv/Scripts/python -m pytest tests -q` (nenhum usa rede) e `cd web && npm test`.

### Criar ou atualizar uma cidade

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
