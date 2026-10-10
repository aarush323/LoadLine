#!/usr/bin/env bash
# Record S0 spike outcomes into docs/spikes.md (append section with timestamp).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/docs/spikes.md"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mkdir -p "$ROOT/docs"

log() { echo "$*" | tee -a "$OUT.run"; }

: >"$OUT.run"
log "# Spike run $TS"
log ""

log "## S-DOCKER"
if docker network create --internal "loadline-spike-$$" 2>/dev/null; then
  NET="loadline-spike-$$"
  if docker run --rm --network "$NET" alpine:3.20 wget -q -T 2 http://1.1.1.1 2>&1 | grep -qiE 'bad address|failed|refused|timeout|Network'; then
    log "- egress from internal network: blocked (pass)"
  else
    log "- egress from internal network: UNEXPECTED success (fail)"
  fi
  docker run -d --name "loadline-spike-a-$$" --network "$NET" alpine:3.20 sleep 300 >/dev/null
  if docker run --rm --network "$NET" alpine:3.20 ping -c1 loadline-spike-a-$$ >/dev/null 2>&1; then
    log "- alias reachability: pass"
  else
    log "- alias reachability: fail"
  fi
  docker rm -f "loadline-spike-a-$$" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null
  PROBE_IMG="curlimages/curl:8.10.1"
  docker pull -q "$PROBE_IMG" >/dev/null
  DIGEST=$(docker image inspect "$PROBE_IMG" --format '{{index .RepoDigests 0}}' 2>/dev/null || true)
  log "- probe candidate image: $PROBE_IMG"
  log "- probe digest: ${DIGEST:-not measured}"
else
  log "- docker unavailable: blocked"
fi
log ""

log "## S-GEN"
K6_IMG="grafana/k6:0.54.0"
if docker pull -q "$K6_IMG" >/dev/null 2>&1; then
  DIGEST=$(docker image inspect "$K6_IMG" --format '{{index .RepoDigests 0}}' 2>/dev/null || true)
  log "- k6 image: $K6_IMG"
  log "- k6 digest: ${DIGEST:-not measured}"
  SUMMARY=$(docker run --rm -i "$K6_IMG" run - <<'EOF' 2>/dev/null | tail -5 || true
import http from 'k6/http';
import { check } from 'k6';
export const options = { vus: 1, iterations: 3 };
export default function () { check(http.get('https://test.k6.io'), { ok: (r) => r.status === 200 }); }
EOF
)
  log "- k6 stdin smoke: ${SUMMARY:-ran}"
else
  log "- k6 pull failed"
fi
log ""

log "## S-CGROUP"
CID=$(docker run -d alpine:3.20 sleep 120 2>/dev/null || true)
if [[ -n "${CID:-}" ]]; then
  STATS=$(docker stats --no-stream --format '{{json .}}' "$CID" 2>/dev/null || true)
  log "- docker stats json sample: ${STATS:0:200}..."
  docker rm -f "$CID" >/dev/null
else
  log "- could not start container for stats"
fi
log ""

log "## S-ENTIRE"
if command -v entire >/dev/null; then
  log "- entire: $(entire version 2>/dev/null | head -1)"
  log "- graph: $(entire graph version 2>/dev/null | head -1)"
  log "- capabilities: $(entire graph capabilities --json 2>/dev/null | head -c 300)"
else
  log "- entire not on PATH; managed install tested via pytest"
fi

# Merge run log into spikes.md
{
  echo ""
  echo "---"
  cat "$OUT.run"
} >>"$OUT"
rm -f "$OUT.run"
echo "Appended to $OUT"
