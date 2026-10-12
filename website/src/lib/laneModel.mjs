import sample from "../data/sample-run.json" with { type: "json" };

const pool = sample.code.pool_size;
const hold = sample.code.hold_s;
const timeout = sample.code.pool_timeout_s;
const serviceMin = sample.code.downstream_ms[0] / 1000;
const serviceMax = sample.code.downstream_ms[1] / 1000;

export function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Discrete pool. Service time is uniform on the recorded downstream range. */
export function simulate(offeredRps, seed = 7) {
  const rng = mulberry32(seed + Math.round(offeredRps * 10));
  const freeAt = Array(pool).fill(0);
  const duration = 20;
  let next = 0;
  let dropped = 0;
  let arrivals = 0;
  const latencies = [];
  const step = 1 / offeredRps;
  while (next < duration) {
    arrivals += 1;
    let idx = 0;
    for (let i = 1; i < pool; i += 1) if (freeAt[i] < freeAt[idx]) idx = i;
    const wait = Math.max(0, freeAt[idx] - next);
    if (wait >= timeout) dropped += 1;
    else {
      const service = serviceMin + rng() * (serviceMax - serviceMin);
      freeAt[idx] = next + wait + service;
      latencies.push((wait + service) * 1000);
    }
    next += step;
  }
  latencies.sort((a, b) => a - b);
  const p50 = latencies.length ? latencies[Math.floor(latencies.length * 0.5)] : 0;
  return { arrivals, dropped, p50 };
}

export function frame(offeredRps) {
  const capacity = pool / hold;
  const busy = Math.max(1, Math.min(pool, Math.ceil(offeredRps * hold)));
  const queue = Math.max(0, Math.round(offeredRps - capacity));
  const shedding = offeredRps >= sample.waves[2].ops[0].offered_rps;
  const instrumentLimit = offeredRps >= sample.waves[1].ops[0].offered_rps;
  return { busy, queue, shedding, instrumentLimit, capacity, pool };
}

export function assertCalibrated(waves) {
  const errors = [];
  for (const wave of waves) {
    const op = wave.ops[0];
    const sim = simulate(op.offered_rps);
    const view = frame(op.offered_rps);
    if (op.dropped === 0 && (sim.dropped > Math.max(1, op.count * 0.05) || view.queue > 0)) {
      errors.push(`low rate ${op.offered_rps} shed or queued (sim dropped ${sim.dropped})`);
    }
    if (op.dropped > 30 && sim.dropped === 0 && !view.shedding) {
      errors.push(`high rate ${op.offered_rps} did not shed`);
    }
    if (op.vus_max >= op.vu_ceiling && !view.instrumentLimit) {
      errors.push(`missing instrument limit at ${op.offered_rps}`);
    }
    if (op.offered_rps <= sample.knee.low_rps && view.instrumentLimit) {
      errors.push(`false instrument limit at ${op.offered_rps}`);
    }
    if (op.offered_rps <= sample.knee.low_rps && (sim.p50 < 250 || sim.p50 > 1200)) {
      errors.push(`simulated p50 ${Math.round(sim.p50)} outside low-rate tolerance`);
    }
  }
  return errors;
}
