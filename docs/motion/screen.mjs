// Gravação de tela do app de verdade, no computador, em Montreal. Um script controla o Chrome (sem tela): move um
// cursor visível, clica nos botões reais e grava o que o navegador mostra (screencast do Chrome). O vídeo sai em
// 1920×1080, 30 fps, com legendas curtas por etapa (o LinkedIn toca sem som).
//
//   node docs/motion/screen.mjs [saida.mp4] [--dry]        (precisa do app em http://127.0.0.1:8000 e de FFMPEG)
// --dry grava só as primeiras etapas, para testar taxa de quadros e visual.
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { launch } from "./cdp.mjs";

const APP = process.env.APP_URL || "http://127.0.0.1:8000";
const args = process.argv.slice(2);
const outFile = args.find((a) => a.endsWith(".mp4")) || "docs/motion/build/uso-no-pc.mp4";
const DRY = args.includes("--dry");
const dir = "docs/motion/build/screen";
rmSync(dir, { recursive: true, force: true });
mkdirSync(dir, { recursive: true });

const PLACES = [ // ordem em que a pessoa marca
  "Notre-Dame Basilica of Montreal", "Montreal Museum of Archaeology and History", "Bonsecours Market",
  "Clock Tower", "Jacques-Cartier Pier", "Vieux-Port de Montréal",
];
const MONTREAL = { lat: 45.5046, lng: -73.5568 }; // Place d'Armes
const FLORIPA = { lat: -27.5969, lng: -48.5495 };

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);

const b = await launch({ width: 1600, height: 900, scale: 1.2, profile: "docs/motion/build/chrome-profile-screen", port: 9444, gpu: process.env.CDP_SOFTWARE !== "1" });
const frames = [];
try {
  // Localização simulada (o app pede a posição sozinho): começa em Florianópolis e vira Montreal na troca de cidade.
  await b.send("Emulation.setLocaleOverride", { locale: "pt-BR" });
  await b.send("Page.addScriptToEvaluateOnNewDocument", {
    source: `try { localStorage.setItem("tv-theme", "light"); } catch {}
      window.__geo = ${JSON.stringify(FLORIPA)};
      Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { getCurrentPosition: (ok) =>
        setTimeout(() => ok({ coords: { latitude: window.__geo.lat, longitude: window.__geo.lng, accuracy: 20 } }), 500) } });`,
  });
  await b.goto(APP);
  if (!(await b.waitFor("document.querySelectorAll('.place').length > 0", 60000))) throw new Error("app não carregou");
  await sleep(2500); // tiles do mapa

  // ── camadas de apresentação: cursor, legenda, abertura e encerramento (no "top layer", acima do pop-up do app) ──
  await b.evaluate(`(() => {
    const css = document.createElement('style');
    css.textContent = \`
      [popover].__ov { position: fixed; inset: auto; margin: 0; padding: 0; border: 0; background: transparent; overflow: visible; color: inherit; }
      #__cursor { left: 0; top: 0; width: 34px; height: 34px; pointer-events: none; opacity: 0; transition: opacity .3s; filter: drop-shadow(0 2px 3px rgba(0,0,0,.35)); }
      #__cursor.on { opacity: 1; }
      [popover].__ripple { width: 20px; height: 20px; border-radius: 50%; border: 4px solid #0e7490; pointer-events: none; transform: translate(-50%,-50%); animation: __rip .65s ease-out forwards; }
      @keyframes __rip { from { width: 14px; height: 14px; opacity: .9 } to { width: 90px; height: 90px; opacity: 0 } }
      #__cap { left: 1148px; top: 26px; transform: translate(-50%, -24px); opacity: 0; transition: opacity .4s, transform .4s; pointer-events: none;
        background: rgba(17,43,58,.94); color: #fff; font: 600 30px 'Segoe UI', system-ui, sans-serif; padding: 14px 30px 14px 16px; border-radius: 999px;
        display: flex; align-items: center; gap: 14px; white-space: nowrap; box-shadow: 0 8px 28px rgba(0,0,0,.3); }
      #__cap.on { opacity: 1; transform: translate(-50%, 0); }
      #__cap b { display: inline-grid; place-items: center; width: 40px; height: 40px; border-radius: 50%; background: #f26b3a; font-size: 24px; }
      [popover].__scene { inset: 0; width: 100vw; height: 100vh; opacity: 0; transition: opacity .9s ease; pointer-events: none;
        background: linear-gradient(180deg, #f7f2e8, #e9e2d2); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18px;
        font-family: 'Segoe UI', system-ui, sans-serif; }
      [popover].__scene.on { opacity: 1; }
      .__scene::before { content: ''; position: absolute; inset: 0 0 auto 0; height: 12px; background: linear-gradient(90deg, #0e7490, #f26b3a); }
      .__scene h1 { margin: 0; font-size: 84px; font-weight: 800; color: #112b3a; letter-spacing: -0.02em; }
      .__scene h2 { margin: 0; font-size: 40px; font-weight: 600; color: #0e7490; }
      .__scene p { margin: 0; font-size: 30px; color: #55707e; }
      .__scene .url { font-size: 38px; font-weight: 800; color: #112b3a; margin-top: 18px; }
      .__scene .tags { display: flex; gap: 14px; margin-top: 10px; }
      .__scene .tags span { background: #d9eef2; color: #0e7490; font-weight: 700; font-size: 24px; padding: 10px 22px; border-radius: 999px; }
    \`;
    document.head.appendChild(css);
    const mk = (id, cls, html) => { const e = document.createElement('div'); e.id = id; e.className = cls; e.setAttribute('popover', 'manual'); e.innerHTML = html; document.body.appendChild(e); return e; };
    const logo = '<svg viewBox="0 0 32 32" width="130" height="130"><defs><linearGradient id="lg" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#f26b3a"/><stop offset="1" stop-color="#0e7490"/></linearGradient></defs><circle cx="16" cy="16" r="15" fill="url(#lg)"/><path d="M7 23 C 11 23, 11 17, 15 17 S 19 12, 22 11" fill="none" stroke="#fff" stroke-width="1.8" stroke-dasharray="2.2 2.2" stroke-linecap="round"/><path d="M22 5.5c-2.6 0-4.5 2-4.5 4.5 0 3.2 4.5 7 4.5 7s4.5-3.8 4.5-7c0-2.5-1.9-4.5-4.5-4.5z" fill="#fff"/><circle cx="22" cy="10" r="1.7" fill="#0e7490"/></svg>';
    const intro = mk('__intro', '__ov __scene on', logo + '<h1>Turista Viajante</h1><h2>Montreal, em um dia</h2><p>Marque os lugares. O solver acha a melhor ordem.</p>');
    const outro = mk('__outro', '__ov __scene', logo + '<h1>Turista Viajante</h1><h2>O melhor caminho para o seu dia de viagem</h2><div class="url">github.com/bbennertz/turista-viajante</div><div class="tags"><span>Python</span><span>OR-Tools CP-SAT</span><span>FastAPI</span><span>React</span><span>MapLibre</span></div>');
    const cap = mk('__cap', '__ov', '<b></b><span></span>');
    const cur = mk('__cursor', '__ov', '<svg viewBox="0 0 24 24" width="34" height="34"><path d="M3 2l7.5 19 2.7-8.1L21 10z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>');
    const order = [cap, cur, intro, outro];
    const show = (e) => { try { e.hidePopover(); } catch {} e.showPopover(); };
    intro.style.transition = 'none'; intro.style.opacity = '1'; outro.style.opacity = '0';
    window.__retop = () => order.forEach(show);          // o pop-up do app entra no top layer: reabrimos as camadas acima dele
    window.__retop();
    window.__cursor = (x, y) => { cur.style.transform = 'translate(' + (x - 4) + 'px,' + (y - 3) + 'px)'; };
    window.__cursorShow = (on) => cur.classList.toggle('on', on);
    window.__ripple = (x, y) => { const r = document.createElement('div'); r.className = '__ov __ripple'; r.setAttribute('popover', 'manual'); r.style.left = x + 'px'; r.style.top = y + 'px'; document.body.appendChild(r); r.showPopover(); setTimeout(() => r.remove(), 750); };
    window.__caption = (n, text) => { if (!text) { cap.classList.remove('on'); return; } cap.querySelector('b').textContent = n; cap.querySelector('span').textContent = text; cap.classList.add('on'); show(cap); show(cur); };
    window.__scene = (which, on) => { const e = document.getElementById(which); e.style.transition = 'opacity .9s ease'; e.style.opacity = on ? '1' : '0'; };
  })()`);

  // ── gravação ────────────────────────────────────────────────────────────────
  b.on("Page.screencastFrame", (p) => {
    const i = frames.length;
    writeFileSync(`${dir}/f${String(i).padStart(5, "0")}.jpg`, Buffer.from(p.data, "base64"));
    frames.push(p.metadata.timestamp);
    b.send("Page.screencastFrameAck", { sessionId: p.sessionId }).catch(() => {});
  });
  await b.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });

  let cx = 800, cy = 520;
  const rect = (expr) => b.evaluate(`(() => { const e = ${expr}; if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`);
  async function moveTo(x, y, ms = 900) {
    const x0 = cx, y0 = cy, dx = x - x0, dy = y - y0, dist = Math.hypot(dx, dy) || 1, arc = Math.min(40, dist * 0.08);
    const t0 = Date.now();
    for (;;) {
      const u = Math.min(1, (Date.now() - t0) / ms), e = ease(u), bend = Math.sin(Math.PI * u) * arc;
      const px = x0 + dx * e - (dy / dist) * bend, py = y0 + dy * e + (dx / dist) * bend;
      await Promise.all([b.evaluate(`__cursor(${px}, ${py})`), b.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: px, y: py })]);
      if (u >= 1) break;
      await sleep(6);
    }
    cx = x; cy = y;
  }
  async function click() {
    await b.evaluate(`__ripple(${cx}, ${cy})`);
    await b.send("Input.dispatchMouseEvent", { type: "mousePressed", x: cx, y: cy, button: "left", clickCount: 1 });
    await sleep(90);
    await b.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: cx, y: cy, button: "left", clickCount: 1 });
  }
  const find = async (expr, what) => { const r = await rect(expr); if (!r) throw new Error(`não achei: ${what}`); return r; };
  const caption = (n, t) => b.evaluate(`__caption(${JSON.stringify(n)}, ${JSON.stringify(t)})`);
  const placeBox = (name) => `[...document.querySelectorAll('.place')].find((p) => p.querySelector('.place-name').textContent.trim() === ${JSON.stringify(name)})?.querySelector('input')`;

  // abertura
  await sleep(1900);
  await b.evaluate(`__scene('__intro', false)`);
  await sleep(1100);
  await b.evaluate(`__cursor(${cx}, ${cy}); __cursorShow(true)`);

  // 1) cidade
  await caption("1", "Escolha a cidade");
  await sleep(700);
  let p = await find(`[...document.querySelectorAll('.city-switch button')].find((x) => x.textContent.startsWith('Montreal'))`, "botão Montreal");
  await moveTo(p.x, p.y, 1100);
  await b.evaluate(`window.__geo = ${JSON.stringify(MONTREAL)}`);
  await click();
  await sleep(3300); // mapa reenquadra e os tiles carregam, localização vira a partida

  // 2) partida
  await caption("2", "A partida vem da sua localização");
  p = await find(`document.querySelector('.hotel-status')`, "linha da partida");
  await moveTo(p.x - 60, p.y, 800);
  await sleep(1800);

  if (!DRY) {
    // 3) lugares
    await caption("3", "Filtre e marque o que visitar");
    p = await find(`[...document.querySelectorAll('.chip')].find((x) => x.textContent.trim() === 'cartão-postal')`, "chip cartão-postal");
    await moveTo(p.x, p.y, 1000);
    await click();
    await sleep(1300);
    for (const name of PLACES) {
      await b.evaluate(`${placeBox(name)}.closest('.place').scrollIntoView({ block: 'center', behavior: 'smooth' })`);
      await sleep(550);
      p = await find(placeBox(name), name);
      await moveTo(p.x, p.y, 600);
      await click();
      await sleep(380);
    }
    await sleep(500);

    // 4) montar
    await caption("4", "O solver acha a melhor ordem");
    p = await find(`document.querySelector('button.primary')`, "botão Montar roteiro");
    await moveTo(p.x, p.y, 1100);
    await click();
    await sleep(1800);
    await b.evaluate(`__retop()`);
    await caption("5", "Horário de chegada em cada lugar");
    await sleep(4500);

    // 5) mapa
    p = await find(`document.querySelector('dialog[open] button.primary')`, "Ver no mapa");
    await moveTo(p.x, p.y, 1000);
    await click();
    await sleep(500);
    await b.evaluate(`__retop()`);
    await caption("6", "A rota, no mapa");
    await moveTo(cx - 120, cy - 260, 800);
    await sleep(3300);

    // 6) Google Maps
    await b.evaluate(`document.querySelector('.result a.btn')?.scrollIntoView({ block: 'center', behavior: 'smooth' })`);
    await sleep(900);
    await caption("7", "E abra a rota no Google Maps");
    p = await find(`document.querySelector('.result a.btn')`, "Abrir no Google Maps");
    await moveTo(p.x, p.y, 900);
    await sleep(2000);
  }

  // encerramento
  await caption("", "");
  await b.evaluate(`__cursorShow(false); __scene('__outro', true)`);
  await sleep(2800);
  await b.send("Page.stopScreencast");
  await sleep(300);
} finally { b.close(); }

// ── monta o MP4 a partir dos quadros e dos instantes em que chegaram ──────────────
const ffmpeg = process.env.FFMPEG;
if (!ffmpeg) throw new Error("defina FFMPEG com o caminho do ffmpeg");
const span = frames[frames.length - 1] - frames[0];
console.log(`${frames.length} quadros do Chrome em ${span.toFixed(1)} s (${(frames.length / span).toFixed(1)} quadros/s)`);
const list = frames.map((t, i) => `file 'screen/f${String(i).padStart(5, "0")}.jpg'\nduration ${Math.min(Math.max((frames[i + 1] ?? t + 1) - t, 0.001), 6).toFixed(4)}`).join("\n");
writeFileSync("docs/motion/build/frames.txt", list + `\nfile 'screen/f${String(frames.length - 1).padStart(5, "0")}.jpg'\n`);
execFileSync(ffmpeg, [
  "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "docs/motion/build/frames.txt",
  "-vf", "fps=30,scale=in_range=pc:out_range=tv,format=yuv420p", "-color_range", "tv", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-movflags", "+faststart", outFile,
], { stdio: "inherit" });
console.log("vídeo:", outFile);
