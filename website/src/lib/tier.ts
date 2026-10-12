export type Tier = 0 | 1 | 2;

type Net = Navigator & {
  deviceMemory?: number;
  connection?: { saveData?: boolean };
};

export function detectTier(): Tier {
  if (typeof window === "undefined") return 0;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return 0;
  const nav = navigator as Net;
  if (nav.connection?.saveData) return 0;
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
    if (!gl) return 0;
  } catch {
    return 0;
  }
  if (nav.deviceMemory && nav.deviceMemory <= 4) return 1;
  return 2;
}
