import { googleMapsLinks } from "../src/maps.ts";
import assert from "node:assert/strict";
const hotel = { lat: -27.589, lng: -48.54 };
const mk = (n) => Array.from({ length: n }, (_, i) => ({ lat: -27 - i / 100, lng: -48 - i / 100 }));
const parse = (u) => { const x = new URL(u); return { o: x.searchParams.get("origin"), d: x.searchParams.get("destination"), w: (x.searchParams.get("waypoints") || "").split("|").filter(Boolean), m: x.searchParams.get("travelmode") }; };

assert.deepEqual(googleMapsLinks(hotel, [], "walk"), []);
let l = googleMapsLinks(hotel, mk(5), "walk"); assert.equal(l.length, 1);
let p = parse(l[0]); assert.equal(p.w.length, 5); assert.equal(p.o, p.d); assert.equal(p.m, "walking");
assert.equal(parse(googleMapsLinks(hotel, mk(2), "car")[0]).m, "driving");
// 9 paradas cabem em 1 link; 10 paradas dividem em 2, encadeadas, sem perder nem repetir paradas
assert.equal(googleMapsLinks(hotel, mk(9), "walk").length, 1);
for (const n of [10, 19, 25]) {
  const links = googleMapsLinks(hotel, mk(n), "walk").map(parse);
  assert.ok(links.every((x) => x.w.length <= 9), "mais de 9 waypoints");
  for (let i = 1; i < links.length; i++) assert.equal(links[i].o, links[i - 1].d, "partes não encadeiam");
  assert.equal(links[0].o, links.at(-1).d, "ida e volta ao hotel");
  const visited = links.flatMap((x, i) => [...x.w, ...(i < links.length - 1 ? [x.d] : [])]);
  assert.equal(visited.length, n, `n=${n}: visitou ${visited.length}`);
  assert.equal(new Set(visited).size, n);
}
console.log("maps.ts ok");
