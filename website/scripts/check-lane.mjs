import { readFileSync } from "node:fs";
import { assertCalibrated } from "../src/lib/laneModel.mjs";

const sample = JSON.parse(readFileSync(new URL("../src/data/sample-run.json", import.meta.url), "utf8"));
const errors = assertCalibrated(sample.waves);
if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("lane model calibrated to recorded sweep");
