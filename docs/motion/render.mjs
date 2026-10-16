// Renderiza a animação quadro a quadro no Chrome (sem tela) e monta o MP4 com o ffmpeg do imageio-ffmpeg.
// Uso (da raiz do projeto, com o servidor estático em docs/motion na porta 8765):
//   node docs/motion/render.mjs [saida.mp4] [--frames=N]      (--frames=N renderiza só os N primeiros, para teste)
import { mkdirSync, writeFileSync, rmSync, readdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { launch } from "./cdp.mjs";

const args = process.argv.slice(2);
const outFile = args.find((a) => !a.startsWith("--")) || "docs/motion/build/turista-viajante-montreal.mp4";
const limit = Number((args.find((a) => a.startsWith("--frames=")) || "").split("=")[1]) || Infinity;
const url = process.env.MOTION_URL || "http://127.0.0.1:8765";
const framesDir = "docs/motion/build/frames";
const profile = process.env.MOTION_PROFILE || "docs/motion/build/chrome-profile";

rmSync(framesDir, { recursive: true, force: true });
mkdirSync(framesDir, { recursive: true });

const b = await launch({ width: 1080, height: 1080, scale: 1, profile });
try {
  await b.goto(`${url}/motion.html`);
  if (!(await b.waitFor("window.__ready === true", 60000))) { console.log(b.logs.slice(-10).join("\n")); throw new Error("animação não ficou pronta"); }
  const fps = await b.evaluate("window.FPS"), total = Math.round((await b.evaluate("window.DURATION")) * fps);
  const n = Math.min(total, limit);
  const t0 = Date.now();
  for (let k = 0; k < n; k++) {
    await b.evaluate(`draw(${k / fps})`);
    writeFileSync(`${framesDir}/f${String(k).padStart(4, "0")}.png`, await b.screenshot("png"));
    if (k % 60 === 0) console.log(`quadro ${k}/${n} (${((Date.now() - t0) / 1000).toFixed(0)} s)`);
  }
  console.log(`${n} quadros em ${((Date.now() - t0) / 1000).toFixed(0)} s`);
} finally { b.close(); }

const ffmpeg = process.env.FFMPEG;
if (!ffmpeg) throw new Error("defina FFMPEG com o caminho do ffmpeg (imageio_ffmpeg.get_ffmpeg_exe())");
execFileSync(ffmpeg, [
  "-y", "-hide_banner", "-loglevel", "error", "-framerate", "30", "-i", `${framesDir}/f%04d.png`,
  "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", outFile,
], { stdio: "inherit" });
console.log("vídeo:", outFile, `(${readdirSync(framesDir).length} quadros)`);
