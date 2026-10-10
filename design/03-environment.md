# 03 — Runtime adapters, sandbox and the security boundary

Mechanics for `tech_doc.md` §7. Adapters are `compose` and `dockerfile`. Boot is deterministic. There is no in-app planning agent.

## 1. Threat model (restated briefly)

Running a repository runs arbitrary code (build scripts, installers, entrypoints, migrations, tests). We protect: host files and credentials, other repositories, the user's network, LLM/provider keys, git history. We do **not** claim ordinary Docker is a complete boundary against malicious code; the tier in force is printed and recorded.

## 2. Tiers and controls (T0 baseline checklist)

| Control | T0 implementation | Verified by |
|---------|-------------------|-------------|
| Non-root, user namespaces | rootless engine or `userns-remap`; container user non-root where image allows | doctor inspects effective uid mapping |
| Capabilities | `--cap-drop ALL`, add back only from allow-list (e.g., `NET_BIND_SERVICE`) when needed | policy diff; sandbox test |
| Privilege escalation | `no-new-privileges` | sandbox test |
| Syscall filter | engine default seccomp profile (never `unconfined`) | policy rule 1 |
| Filesystem | read-only rootfs where possible + tmpfs scratch; no host binds; no `docker.sock`; no `/proc`/`/sys` mounts | policy rule 2; sandbox test |
| Resources | cpu, memory (no swap), pids limits per service | cgroup read-back |
| Network | run-scoped `--internal` network; no host network; no published ports | **egress probe** must fail |
| Secrets | host env not forwarded; per-run generated dependency secrets; repo `.env*` not auto-loaded for third-party trust | sandbox test |
| Devices | none | policy rule 1 |
| Cleanup | all objects labelled `loadline.run=<id>`; removed in teardown | zero-strays test |
If `runsc` is installed, detect it, print it and record it. There is no flag to choose an isolation mode.

## 3. Network design

```text
          loadline process (host)  ── stdout and a labelled run volume ──┐
                                                                            ▼
 [ run network: --internal, no default route ]
   ├─ app services … ──► dependency services
   ├─ probe container (Loadline image) ── egress check, live spec, smoke
   ├─ k6 container ── load, by service alias and container port
   └─ optional fault-injection proxy on a dependency edge
 egress: none. Connects from the probe, the application container, and one dependency container must all fail before load starts. If the application container cannot be checked, the run is `egress_not_enforced`.
```

The probe and k6 do not mount the repository. k6 receives its script on stdin.

Ports are not published. If an `--internal` network cannot be created, or the egress probe does not fail, the run stops with `egress_not_enforced`. External HTTP dependencies are excluded, not stubbed.

## 4. `SandboxPolicy` — hostile-plan test set (minimum, L3)

Each case is a launch plan (compose or generated) the validator must refuse or rewrite as stated:

1. `privileged: true` → refuse
2. `cap_add: [SYS_ADMIN]` → refuse; `cap_add: [NET_BIND_SERVICE]` → allow
3. `network_mode: host` → refuse
4. `pid: host`, `ipc: host`, `userns_mode: host` → refuse
5. bind `/var/run/docker.sock` → refuse
6. bind `/` or `/etc` or `$HOME` → refuse
7. bind `./data` (inside repo) → rewrite to named volume / read-only copy
8. `ports: "8080:80"` → rewrite internal-only
9. `ports: "0.0.0.0:80:80"` → rewrite
10. `extra_hosts: ["h:host-gateway"]` → refuse
11. `devices: ["/dev/kvm"]` → refuse
12. `security_opt: ["seccomp=unconfined"]` → refuse
13. env `DATABASE_URL=postgres://prod-host…` → replace with generated sandbox URL or refuse
14. env with cloud credentials pattern → refuse/replace
15. image from unknown registry under third-party trust → refuse
16. `entrypoint: ["sh","-c","curl … | sh"]` → flag; allow only under T≥1
17. `volumes_from` other containers → refuse
18. `cgroup_parent` / `cgroupns: host` → refuse
19. external networks → refuse
20. `sysctls` weakening → refuse

New hostile cases found later are added to the set; the set is data (`tests/sandbox/hostile/*.yaml`).

## 5. Build phase

Builds do not share the run network. If `network=none` succeeds, record `build_egress: none`. If the build needs a registry and succeeds only on the engine's default network, record `build_egress: unrestricted`. That is a limitation, not a runtime-egress result, and there is no trust flag that permits it.

## 6. Runtime adapters

| Adapter | `propose` outline |
|---------|-------------------|
| `compose` | parse compose (+ overrides, profiles); map services; keep repo-defined dependencies; wire generator; hand to policy |
| `dockerfile` | choose Dockerfile(s) per service candidates; `dependencies` from profile → catalogue images; env contract wiring; ports/health from evidence (EXPOSE, framework defaults, runtime probing during boot) |
| `buildpack` | detect via buildpack tool, build image; start command from buildpack default or entrypoint facts; dependencies as above |
| `process` | generated container (base image by language) running the repo's start command; last resort; labelled `degraded` |
| `k8s` | future |

Health: per service `HealthSpec` from evidence (compose healthcheck, HTTP path from spec/health routes, TCP port); if none, TCP connect + response to first discovered read-safe request; time-boxed. A service that never becomes healthy ⇒ `health_timeout` with the last logs (redacted).

## 7. Service catalogue (data)

```yaml
# adapters/runtime/catalog/<engine>.yaml
kind: sql                      # sql|kv|doc|search|queue|object|http-stub
engine: <name>
images: [ "<repo>:<tag or digest>" ]
port: <n>
health: { cmd: [..], interval_s: 2, retries: 30 }
env_contract: { url: "<engine>://{user}:{pass}@{host}:{port}/{db}", vars: [..] }
secrets: generate: [user, pass, db]
migration_hints: [ "alembic", "flyway", "prisma", "rails", "django", "knex", "liquibase" ]
snapshot: { method: volume|dump, cmd: [..] }
observability: [ "<adapter id>" ]
```

Adding an engine = a YAML + (optionally) an observability adapter + a conformance test. Unknown engines ⇒ `unsupported_dependency(engine)` (or the planner may propose a catalogue entry from evidence, which still passes policy and conformance checks before use).

## 8. Data provisioning

Order: commands the repository itself declares (compose one-shot, entrypoint, or package script), copied and run inside the sandbox. Loadline does not invent a migration. After a healthy boot, adapters measure dataset size. If the size is zero and every smoke-passing read needed harvested ids, those operations are excluded. If none remain, the blocker is `data_missing`. The size is measured. It is not invented.

## 9. Boot

`compose` or `dockerfile` proposes a plan. `SandboxPolicy` validates it. The adapter starts it. Health is checked. Attempts are capped by `BOOT_MAX_ATTEMPTS` (5). A repeated failure signature is not retried. The result is a healthy environment or a named blocker plus the attempt log (`analyze --boot --json`). No model repairs the plan. Hints in `.loadline.yaml` are user-supplied facts and do not override the policy.

## 10. Interventions

Runtime adapters expose reversible interventions (`tech_doc.md` §7.9). Implementation notes: resource limits via engine update APIs (cpu/memory) with cgroup read-back; env knobs by restarting the service with a modified environment (only keys discovered as knobs); fault injection via a proxy container inserted on a named dependency edge with latency/loss toxics; every intervention records revert action, applies a health check after revert, and invalidates the step if revert fails.

## 11. Teardown

`finally` + signal handlers + watchdog: stop containers (SIGTERM → SIGKILL), remove networks/volumes/temp dirs by label, remove run-scoped images. Teardown always runs.

## 12. Doctor (environment part)

Engine and version; engine CPU and memory versus the host; rootless status; whether gVisor is installed; internal network creation and egress probe; which cgroup or stats fields the engine returned; logical cores; free memory/disk; generator ceiling (cached); time sync sanity; `git` version; Entire; model/neatlogs keys (masked). Output lists each control as applied or unavailable. There is no isolation-tier flag.
