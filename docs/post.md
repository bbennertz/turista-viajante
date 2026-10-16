# Post do LinkedIn

Um único post, em português e inglês, para colar direto no LinkedIn (o LinkedIn não renderiza Markdown, então o texto é simples).
O limite do LinkedIn é 3.000 caracteres: o trecho abaixo da linha `---` inicial tem de caber nisso (hoje tem cerca de 2.400).
Anexos sugeridos: `turista-viajante-montreal-uso-no-pc.mp4` (vídeo) e `docs/formulacao.png` (formulação).

---

[ENGLISH BELOW]

Durante o intercâmbio, nem sempre estudar é a prioridade.

Na "semana do saco cheio" fui turistar e fiquei bravo: passei duas vezes em frente ao mesmo lugar, fruto de um roteiro mal planejado. Lembrei das aulas de Pesquisa Operacional: eu já tinha modelado algo parecido, o caixeiro viajante (TSP), que visita todos os pontos de um grafo minimizando a distância ou o tempo. Aproveitei o dia chuvoso e montei o "Turista Viajante" (o nome ainda cabe melhorias, eu sei).

Como funciona: busco os pontos turísticos na API do Google Places, um LLM classifica cada lugar pela atividade, eu marco os que quero visitar e um modelo de otimização (CP-SAT, do OR-Tools) monta o roteiro de um dia, saindo e voltando ao hotel e respeitando os horários de funcionamento. Se não couber no dia, o app explica o porquê. O resultado aparece no mapa, com o horário de chegada em cada lugar, e a rota abre no Google Maps.

Para completar, deixei o front-end bonitinho e pedi pro Claude montar esse post. Como próximos passos, quero contabilizar o transporte público nos deslocamentos e expandir os pontos turísticos e as cidades.

Código: github.com/bbennertz/turista-viajante

#PesquisaOperacional #OperationsResearch #Python #ORTools

---

During my exchange semester, studying isn't always the priority.

In our "fed-up week" (a break from classes) I went sightseeing and got annoyed: I walked past the same spot twice, the result of a badly planned route. I remembered my Operations Research classes: I had already modeled something similar, the Traveling Salesman Problem (TSP), which visits every node of a graph while minimizing distance or time. I used a rainy day to build my own "Turista Viajante" (the name could use some work, I know).

How it works: I pull attractions from the Google Places API, an LLM tags each place by activity, I tick the ones I want to visit, and an optimization model (CP-SAT, from OR-Tools) builds a one-day route that leaves and returns to the hotel and respects opening hours. If it doesn't fit in the day, the app explains why. The result shows on a map with the arrival time at each place, and the route opens in Google Maps.

To top it off, I made the front end look nice and asked Claude to write this post. As next steps, I want to account for public transit in travel times and expand the attractions and cities.

Code: github.com/bbennertz/turista-viajante

#OperationsResearch #Python #ORTools
