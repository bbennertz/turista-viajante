# docs

- `formulacao.html`: peça 1080×1350 (vertical, para o feed do LinkedIn) com a formulação matemática do solver.
  Usa KaTeX via CDN, então precisa de internet ao renderizar.
- `formulacao.png`: a mesma peça em 2160×2700 (2×).

Para regenerar o PNG depois de editar o HTML (Chrome instalado, sem nada mais):

```bash
"/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu --hide-scrollbars \
  --window-size=1080,1350 --force-device-scale-factor=2 --virtual-time-budget=20000 \
  --screenshot=docs/formulacao.png "file:///$(pwd -W)/docs/formulacao.html"
```

`--virtual-time-budget` dá tempo para o KaTeX carregar e desenhar as fórmulas; sem ele a imagem sai com o código
LaTeX cru. A altura é fixa em 1350 px: se o conteúdo crescer, o rodapé é cortado, então confira o resultado.

## motion/: vídeo de divulgação (1080×1080, 30 fps, 20 s)

Animação do app em Montreal, desenhada em canvas: cada quadro é uma função pura do tempo (`draw(t)`), então o
movimento é perfeitamente suave e reproduzível. Os horários e a rota vêm do roteiro real que o app calculou
(`data.json`, versionado: é a resposta da API para os 6 lugares escolhidos); o mapa-base é o mesmo do app (OpenFreeMap).

```bash
# da raiz do projeto, com o Chrome instalado (o data.json já está no repositório)
python -m http.server 8765 --directory docs/motion &                 # servidor estático da animação
node docs/motion/basemap.mjs docs/motion/build                      # mapa-base em alta resolução + posições em pixel
export FFMPEG="$(.venv/Scripts/python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
node docs/motion/render.mjs                                         # 600 quadros -> docs/motion/build/*.mp4 (~3,5 min)
```

- `node docs/motion/stills.mjs 6,10.4,17` gera quadros de prévia nos tempos pedidos (para ajustar o visual).
- No navegador, abra `motion.html` e rode `play()` no console para ver ao vivo.
- Dependências: Node 22+ (cliente WebSocket nativo), Chrome, e `imageio-ffmpeg` (em `requirements-dev.txt`) só para
  codificar o MP4. `docs/motion/build/` fica fora do Git.

## motion/screen.mjs: gravação do app em uso (1600×900, ~50 s)

Grava o app de verdade rodando no Chrome (cursor, cliques, mapa, modal), no estilo de demonstração de produto: zoom suave
que acompanha a ação, sem abertura nem encerramento, legendas em português e geolocalização simulada na Place d'Armes, em Montreal. Não mostra Genebra. O app e a API precisam estar no ar (ver README principal).

```bash
export FFMPEG="$(.venv/Scripts/python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
node docs/motion/screen.mjs docs/motion/build/uso-no-pc.mp4        # --dry ensaia sem codificar
```

Usa a GPU (`--use-angle=d3d11`) para chegar a ~18 quadros/s; com renderização por software ficava em ~5.
