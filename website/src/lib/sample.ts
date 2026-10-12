import sample from "../data/sample-run.json";

export type Sample = typeof sample;

export const sampleRun: Sample = sample;

export function lookup(src: string): string | number {
  let cur: unknown = sample;
  for (const part of src.split(".")) {
    if (cur == null || typeof cur !== "object" || !(part in (cur as object))) {
      throw new Error(`Unknown datum ${src}`);
    }
    cur = (cur as Record<string, unknown>)[part];
  }
  if (typeof cur === "number" || typeof cur === "string") return cur;
  throw new Error(`Datum ${src} is not a scalar`);
}

export type Op = Sample["waves"][number]["ops"][number];

export function ops(): Op[] {
  return sample.waves.map((wave) => wave.ops[0]);
}

export function p95At(rps: number): number {
  const pts = ops().map((op) => ({ x: op.offered_rps, y: op.p95_ms }));
  if (rps <= pts[0].x) return pts[0].y * (0.35 + 0.65 * (rps / pts[0].x));
  for (let i = 1; i < pts.length; i += 1) {
    if (rps <= pts[i].x) {
      const t = (rps - pts[i - 1].x) / (pts[i].x - pts[i - 1].x);
      return pts[i - 1].y + t * (pts[i].y - pts[i - 1].y);
    }
  }
  return pts[pts.length - 1].y;
}

export function nearestOp(rps: number): Op {
  return ops().reduce((best, op) =>
    Math.abs(op.offered_rps - rps) < Math.abs(best.offered_rps - rps) ? op : best,
  );
}
