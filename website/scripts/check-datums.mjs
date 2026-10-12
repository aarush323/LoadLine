import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const sample = JSON.parse(readFileSync(new URL("../src/data/sample-run.json", import.meta.url), "utf8"));

function lookup(src) {
  let cur = sample;
  for (const part of src.split(".")) {
    if (cur == null || typeof cur !== "object" || !(part in cur)) return undefined;
    cur = cur[part];
  }
  return cur;
}

function walk(dir, acc = []) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path, acc);
    else if (name.endsWith(".tsx")) acc.push(path);
  }
  return acc;
}

const forbidden = ["541", "816", "3022", "5529", "5004", "5641", "5214", "5706", "1003", "282"];
const errors = [];

for (const file of walk(new URL("../src", import.meta.url).pathname)) {
  const text = readFileSync(file, "utf8");
  for (const hit of forbidden) {
    if (text.includes(hit)) errors.push(`${file} hardcodes recorded metric ${hit}`);
  }
  for (const match of text.matchAll(/<Datum\b([^>]*)>/g)) {
    const attrs = match[1];
    const src = attrs.match(/\bsrc="([^"]+)"/)?.[1];
    const templated = attrs.match(/\bsrc=\{`([^`$]+)`\}/)?.[1];
    const dynamic = /\bsrc=\{/.test(attrs);
    const illustrative = /\billustrative\b/.test(attrs);
    if (!src && !templated && !dynamic && !illustrative) errors.push(`${file} Datum missing src or illustrative`);
    if (src && typeof lookup(src) !== "number" && typeof lookup(src) !== "string") {
      errors.push(`${file} Datum src not in sample-run.json: ${src}`);
    }
    if (templated && !templated.includes("${")) {
      if (typeof lookup(templated) !== "number" && typeof lookup(templated) !== "string") {
        errors.push(`${file} Datum src not in sample-run.json: ${templated}`);
      }
    }
  }
}

if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("datum sources resolve");
