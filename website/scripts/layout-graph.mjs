import { writeFileSync } from "node:fs";

/** Layered left-to-right layout. The site imports the JSON; it does not lay out at runtime. */
const layers = [["op"], ["handler"], ["branch"], ["acquire", "downstream"], ["pool", "compute"], ["other"]];

const nodes = [];
layers.forEach((layer, i) => {
  layer.forEach((id, j) => {
    const y = layer.length === 1 ? 210 : 110 + j * 190;
    nodes.push({ id, x: 140 + i * 155, y });
  });
});

writeFileSync(new URL("../src/data/graph-layout.json", import.meta.url), JSON.stringify({ nodes }, null, 2) + "\n");
