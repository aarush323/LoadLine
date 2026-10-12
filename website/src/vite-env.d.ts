/// <reference types="vite/client" />

declare module "*.css";

interface Window {
  UnicornStudio?: { isInitialized: boolean; init?: () => void };
}

declare module "../lib/laneModel.mjs" {
  export function frame(offeredRps: number): {
    busy: number;
    queue: number;
    shedding: boolean;
    instrumentLimit: boolean;
    capacity: number;
    pool: number;
  };
}
