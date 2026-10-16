import { distanceKm, locate, MAX_KM_FROM_CITY } from "../src/geo.ts";
import assert from "node:assert/strict";
const floripa = { lat: -27.5969, lng: -48.5495 };
// haversine: Floripa -> São Paulo ≈ 495 km; ponto contra si mesmo = 0; simetria
const sp = { lat: -23.5505, lng: -46.6333 };
assert.ok(Math.abs(distanceKm(floripa, sp) - 495) < 15, String(distanceKm(floripa, sp)));
assert.equal(distanceKm(floripa, floripa), 0);
assert.equal(distanceKm(floripa, sp), distanceKm(sp, floripa));
const ok = (lat, lng) => ({ getCurrentPosition: (s) => s({ coords: { latitude: lat, longitude: lng } }) });
const fail = (code) => ({ getCurrentPosition: (_s, e) => e({ code }) });
let r = await locate(floripa, "Florianópolis", ok(-27.60, -48.50)); assert.ok(r.ok && r.distance < 10);
r = await locate(floripa, "Florianópolis", ok(sp.lat, sp.lng)); assert.ok(!r.ok && r.reason === "far" && /Você está a \d{3} km de Florianópolis/.test(r.message) && r.message.includes("Florianópolis"));
r = await locate(floripa, "Florianópolis", fail(1)); assert.ok(!r.ok && r.reason === "denied");
r = await locate(floripa, "Florianópolis", fail(2)); assert.ok(!r.ok && r.reason === "unavailable");
r = await locate(floripa, "Florianópolis", fail(3)); assert.ok(!r.ok && r.reason === "timeout");
r = await locate(floripa, "Florianópolis", undefined); assert.ok(!r.ok && r.reason === "unsupported");
// limite: exatamente na borda de 60 km ainda é aceito; um pouco além, não
const edge = (km) => ok(floripa.lat + km / 111.19, floripa.lng);
assert.ok((await locate(floripa, "x", edge(MAX_KM_FROM_CITY - 1))).ok);
assert.ok(!(await locate(floripa, "x", edge(MAX_KM_FROM_CITY + 1))).ok);
console.log("geo.ts ok");
