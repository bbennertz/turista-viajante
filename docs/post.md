# Post do LinkedIn

Um único post, em português e inglês, para colar direto no LinkedIn (o LinkedIn não renderiza Markdown, então o texto é simples).
Anexos sugeridos: `turista-viajante-montreal-uso-no-pc.mp4` (vídeo) e `docs/formulacao.png` (formulação).

---

[ENGLISH BELOW]

Durante o intercâmbio, nem sempre estudar é a prioridade.

Essa semana estávamos na "semana do saco cheio" e aproveitei para conhecer melhor a cidade. No último dia em que saí para turistar, fiquei bravo: passei duas vezes em frente ao mesmo lugar. Fruto de um roteiro mal estruturado, eu sei.

Foi aí que lembrei das aulas de Pesquisa Operacional. Eu já tinha modelado um problema muito parecido, o caixeiro viajante (TSP): passar por todos os pontos de um grafo minimizando a distância ou o tempo. Aproveitei o dia chuvoso e montei o meu "Turista Viajante" (o nome ainda cabe melhorias, eu sei).

Como funciona:
- Busco os principais pontos turísticos da cidade na API do Google Places.
- Um LLM lê as avaliações e classifica cada lugar pela atividade (museu, mirante, parque, mercado...).
- Eu marco numa lista os lugares que quero visitar.
- Um modelo de otimização (CP-SAT, do OR-Tools) monta o roteiro de um dia: sai do hotel, respeita os horários de funcionamento, visita todos os lugares marcados e volta ao hotel, minimizando o deslocamento. Se não couber no dia, o app explica o porquê em vez de só dizer "não deu".
- O resultado aparece no mapa, com o horário de chegada em cada lugar, e a rota abre direto no Google Maps.

Para completar, deixei o front-end bonitinho e pedi pro Claude montar esse post.

Agora consigo turistar e aplicar Pesquisa Operacional ao mesmo tempo.

Código: github.com/bbennertz/turista-viajante

#PesquisaOperacional #OperationsResearch #Python #ORTools #LLM #Montreal

---

During my exchange semester, studying isn't always the priority.

This week was our "fed-up week" (a break from classes), so I used it to see more of the city. On my last sightseeing day I got annoyed: I walked past the same spot twice. The result of a badly planned route, I know.

That's when I remembered my Operations Research classes. I had already modeled a very similar problem, the Traveling Salesman Problem (TSP): visit every node of a graph while minimizing distance or time. I took advantage of a rainy day and built my own "Turista Viajante" (the name could use some work, I know).

How it works:
- I pull the city's main attractions from the Google Places API.
- An LLM reads the reviews and tags each place by activity (museum, viewpoint, park, market...).
- I tick the places I want to visit in a list.
- An optimization model (CP-SAT, from OR-Tools) builds a one-day route: it leaves the hotel, respects opening hours, visits every ticked place and returns to the hotel, minimizing travel. If it doesn't fit in the day, the app explains why instead of just saying "no solution".
- The result shows on a map with the arrival time at each place, and the route opens straight in Google Maps.

To top it off, I made the front end look nice and asked Claude to write this post.

Now I can be a tourist and apply Operations Research at the same time.

Code: github.com/bbennertz/turista-viajante

#OperationsResearch #Python #ORTools #LLM #StudyAbroad #Montreal
