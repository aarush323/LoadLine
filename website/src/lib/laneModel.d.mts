export function frame(offeredRps: number): {
  busy: number;
  queue: number;
  shedding: boolean;
  instrumentLimit: boolean;
  capacity: number;
  pool: number;
};
