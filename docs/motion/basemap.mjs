// Gera o mapa-base da animação (PNG 2×) e as posições em pixel dos pontos. Uso: node basemap.mjs <pasta-de-saída>
import { writeFileSync } from "node:fs";
import { launch } from "./cdp.mjs";

const out = process.argv[2];
const url = process.env.MOTION_URL || "http://127.0.0.1:8765";
const b = await launch({ width: 1080, height: 1080, scale: 2, profile: `${out}/chrome-profile` });
try {
  await b.goto(`${url}/basemap.html`);
  const ok = await b.waitFor("document.title === 'ready'", 90000);
  console.log("mapa pronto:", ok);
  if (!ok) { console.log(b.logs.slice(-15).join("\n")); process.exitCode = 1; }
  else {
    await new Promise((r) => setTimeout(r, 1500)); // deixa os últimos rótulos assentarem
    writeFileSync(`${out}/pixels.json`, await b.evaluate("document.getElementById('out').textContent"));
    writeFileSync(`${out}/basemap.png`, await b.screenshot("png"));
    console.log("salvo em", out);
  }
} finally { b.close(); }
