// Prévia: renderiza quadros em tempos escolhidos. Uso: node docs/motion/stills.mjs 1,6,9.2 [pasta]
import { mkdirSync, writeFileSync } from "node:fs";
import { launch } from "./cdp.mjs";

const times = (process.argv[2] || "1,6,10,13,17,19.5").split(",").map(Number);
const dir = process.argv[3] || "docs/motion/build/stills";
mkdirSync(dir, { recursive: true });
const b = await launch({ width: 1080, height: 1080, scale: 1, profile: process.env.MOTION_PROFILE || "docs/motion/build/chrome-profile" });
try {
  await b.goto(`${process.env.MOTION_URL || "http://127.0.0.1:8765"}/motion.html`);
  if (!(await b.waitFor("window.__ready === true", 60000))) { console.log(b.logs.slice(-10).join("\n")); throw new Error("não ficou pronto"); }
  for (const t of times) {
    await b.evaluate(`draw(${t})`);
    writeFileSync(`${dir}/t${String(t).replace(".", "_")}.png`, await b.screenshot("png"));
    console.log("ok", t);
  }
} finally { b.close(); }
