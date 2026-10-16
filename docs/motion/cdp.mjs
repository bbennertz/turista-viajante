// Cliente mínimo do Chrome DevTools Protocol (Node 22+, sem dependências): abre o Chrome sem tela, navega,
// executa JS e tira capturas em tamanho e escala exatos. Usado para renderizar o mapa-base e os quadros do vídeo.
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";

export async function launch({ width, height, scale = 1, profile, port = 9333 }) {
  profile = resolve(profile); // o Chrome exige caminho absoluto no perfil
  mkdirSync(profile, { recursive: true });
  const proc = spawn(
    CHROME,
    [
      "--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
      "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
      "--hide-scrollbars", "--no-first-run", "--disable-background-timer-throttling",
      "--disable-renderer-backgrounding", `--window-size=${width},${height}`, "about:blank",
    ],
    { stdio: "ignore" },
  );
  let target;
  for (let i = 0; i < 60 && !target; i++) {
    await new Promise((r) => setTimeout(r, 250));
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
      target = list.find((t) => t.type === "page");
    } catch { /* Chrome ainda subindo */ }
  }
  if (!target) { proc.kill(); throw new Error("Chrome não respondeu na porta de depuração"); }

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const pending = new Map();
  const logs = [];
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) {
      const { res, rej } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result);
    } else if (msg.method === "Runtime.consoleAPICalled") {
      logs.push(`[console.${msg.params.type}] ${msg.params.args.map((a) => a.value ?? a.description).join(" ")}`);
    } else if (msg.method === "Runtime.exceptionThrown") {
      logs.push(`[exceção] ${msg.params.exceptionDetails.exception?.description ?? msg.params.exceptionDetails.text}`);
    } else if (msg.method === "Log.entryAdded") {
      logs.push(`[log.${msg.params.entry.level}] ${msg.params.entry.text} ${msg.params.entry.url ?? ""}`);
    }
  };
  const send = (method, params = {}) => new Promise((res, rej) => {
    const i = ++id;
    pending.set(i, { res, rej });
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable");
  await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: scale, mobile: false });

  const evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    return r.result.value;
  };
  const goto = async (url) => {
    await send("Page.navigate", { url });
    for (let i = 0; i < 400; i++) { // espera o load
      if ((await evaluate("document.readyState")) === "complete") return;
      await new Promise((r) => setTimeout(r, 100));
    }
    throw new Error("página não terminou de carregar");
  };
  const waitFor = async (expression, ms = 60000) => {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
      if (await evaluate(expression)) return true;
      await new Promise((r) => setTimeout(r, 250));
    }
    return false;
  };
  const screenshot = async (format = "png", quality) => {
    const r = await send("Page.captureScreenshot", { format, quality, captureBeyondViewport: false });
    return Buffer.from(r.data, "base64");
  };
  const close = () => { try { ws.close(); } catch {} proc.kill(); };
  return { send, evaluate, goto, waitFor, screenshot, close, logs };
}
