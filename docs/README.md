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
