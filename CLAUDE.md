# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Projeto pessoal de portfólio (Bruno): o usuário marca lugares turísticos de uma cidade e o app devolve a melhor
ordem de **um dia**, saindo e voltando ao hotel. Textos de interface, mensagens e comentários são em português.

## Comandos

Python vive em `.venv` (Windows; use `.venv/Scripts/python`). Sempre rode a partir da raiz.

```bash
.venv/Scripts/python -m pytest tests -q                         # todos os testes (nenhum usa rede)
.venv/Scripts/python -m pytest tests/solver/test_tsp.py::test_name -q   # um teste
cd web && npm test                                              # testes JS (geo.ts, maps.ts)
cd web && npm run build                                         # tsc --noEmit + vite build -> web/dist
.venv/Scripts/python -m uvicorn api.main:app --port 8000        # API + front buildado (sem hot reload)
cd web && npm run dev                                           # Vite com proxy de /api para :8000
```

- A API serve `web/dist`: mudança no front exige `npm run build`; mudança em Python exige **reiniciar o uvicorn**.
- Pipeline de dados por cidade (retomável, cada etapa pula o que já existe em disco):
  `scripts/build_city.py <cidade> [collect]` (descoberta → detalhes → classificação → merge),
  `scripts/refresh_matrices.py <cidade> [full]` (matrizes a pé e de carro),
  `scripts/classify_city.py <cidade>` (só classificação, com espera de 10 min quando a cota da Groq acaba).
- Chaves em `.env` (criado por `scripts/setup_keys.sh`): `GOOGLE_PLACES_API_KEY`, `GROQ_API_KEY`;
  opcionais `ORS_API_KEY`, `ROUTING_PROVIDER` (`osrm` padrão | `ors`), `LLM_MODEL`.

## Arquitetura

Duas metades ligadas por arquivos em `data/cities/<id>/`:

**Offline (`pipeline/`)** produz os dados. `city.json` (regiões, bbox, idioma) → `agent.py` (agente LangGraph que
decide as buscas no Google Places; o código impõe orçamento, deduplicação e mínimos por tipo) → `candidates.json` →
`details.py` → `details/*.json` → `classify.py` (LLM na Groq extrai um vetor de features por lugar) →
`classified/*.json` → `merge.py` → `places.json` (+ `coverage.json`) → `matrix.py` → `matrix_walk|car.json`.
`city.py` guarda só configuração/geografia (sem LLM). `places.py` tem um livro-caixa (`data/ledger.json`) que
bloqueia chamadas pagas do Google acima de 800/mês.

**Online** : `api/main.py` (FastAPI) → `api/places.py` (lista do checkbox) e `api/route.py` (`plan_route`) → `solver/tsp.py`.
`plan_route` carrega a matriz da cidade, calcula a linha do hotel **ao vivo** (`matrix.hotel_times`, um único pedido) e,
se o serviço de rotas falhar, cai em `proxy_hotel_times` (lugar mais próximo) e avisa na resposta. O front
(`web/`, React + Vite + MapLibre) fica em `App.tsx`, que guarda o estado e um *snapshot* das entradas do último cálculo.

**Solver v1 (`solver/tsp.py`)**: TSP com janelas de horário de um dia, todos os lugares marcados obrigatórios,
CP-SAT com `AddCircuit`. Objetivo lexicográfico em uma resolução: `2048·deslocamento + hora de volta`. Usa o fecho
métrico da matriz. Inviável devolve explicação: causas óbvias → certificado (visitas + menor TSP > janela do dia) →
menor subconjunto em conflito por remoção. Horário não convexo entra como domínio (`AddLinearExpressionInDomain`).

**Código da v2, guardado e fora do caminho da v1**: `solver/model.py` (modelo monolítico, baseline), `benders.py`
(decomposição lógica de Benders, 3 estágios), `scoring.py` (estilos/score/pool top-K), `api/itinerary.py`. Não reintroduza
estilos, score, pool ou restaurantes na v1 sem o usuário pedir (decisão dele; "Como um local" está em `DISABLED_PRESETS`).

## Material de divulgação

`docs/` guarda a imagem da formulação (HTML + PNG) e `docs/motion/` (animação em canvas -> MP4 via Chrome sem tela +
ffmpeg); os comandos de renderização estão em `docs/README.md`. Não commite `docs/motion/build/`.

## Armadilhas

- **Unidades:** minutos desde 00:00; no solver `weekday` 0 = segunda, mas o Google numera 0 = domingo (convertido em
  `hours.py`). Lugar sem horário no Google = sempre aberto (decisão do usuário).
- **Matrizes de provedores diferentes não se misturam** (OSRM dá ~12% mais que o ORS): cada arquivo registra
  `provider`, e `refresh_matrices.py` reconstrói tudo se ele mudou. Só grava as duas matrizes se ambas derem certo.
- **OSRM público atrasa pedidos em sequência (~10 s)**: por isso a linha do hotel é um único pedido, com limite
  curto (15 s × 2) ao vivo. O ORS tem cota separada para a Matrix API e pode ficar bloqueado por horas.
- **A API só lista lugares presentes em TODAS as matrizes** (`routable_ids`); um `places.json` novo sem matriz nova
  esconde os lugares novos em vez de quebrar. Depois de `merge`, refaça as matrizes.
- **A API não pode importar langgraph/langchain** (a imagem Docker não os instala; há teste). Configuração de cidade
  usada pela API fica em `pipeline/city.py`, não em `agent.py`.
- **Tema e mapa-base:** `web/src/theme.ts` (claro/escuro, escolha guardada em `localStorage`, senão segue o sistema); as cores
  vêm de variáveis CSS (`--accent`, `--sun`, `--map-*`) e o mapa as lê ao recriar as camadas. O mapa-base é o vetorial do
  OpenFreeMap (`positron`/`dark`, sem chave); os tiles raster da CARTO passaram a exigir chave. Ao trocar de estilo
  (`setStyle`) as camadas somem e são recriadas no evento `style.load`.
- **Google Places:** peça só os campos usados. Em `reviews` use `reviews.rating`/`reviews.text` (o campo inteiro traz nome,
  foto e perfil dos autores); há teste. `places.json` nunca leva o campo `evidence` (trechos de reviews).
- **Não commite dados brutos:** `details/`, `classified/`, `candidates.json` e respostas cruas da API ficam fora do Git.
- **MapLibre 6 no Vite:** o worker precisa de `import ...maplibre-gl-worker.mjs?worker&url` + `setWorkerUrl`; sem isso
  os pontos e a linha do roteiro (fontes GeoJSON) nunca aparecem, só os tiles.
- **Groq grátis:** 200 mil tokens/dia por modelo; o prompt usa `CONTRACT` compacto (não o JSON Schema) para caber.
  Classificação é retomável (`classified/<id>.json` por lugar).
- Testes de API trocam `api.route.hotel_times` em `tests/conftest.py`; não deixe teste novo depender de rede.
- `Dockerfile` (Hugging Face Spaces, porta 7860) **nunca foi construído**: não havia Docker na máquina.
- Cuidado ao colar heredocs longos com aspas no Bash: prefira criar arquivos pelas ferramentas de edição.
