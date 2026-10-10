# 10 — v3 review: contradictions resolved, residual risks, anti-overfitting audit

Written for the product direction reset of 2026-10-10. It replaces the v2 adversarial review (copy in `.archive-pre-reset/design/10-review.md`).

## 1. Conflicts found in the v2 doc set and their resolution

| Conflict (v2) | Resolution (v3) | Where defined |
|---------------|-----------------|---------------|
| Tool counts: 4, 8, 11 and 12 in older drafts | Seven Investigator tools | `tech_doc.md` §11.3 |
| Load engine: Locust spec vs k6 | k6 behind `GeneratorAdapter`; other generators are optional adapters | `tech_doc.md` D3 |
| Spec "Testability Manifest" vs "operations manifest" | one `RepoProfile` + `OperationDescriptor`; provenance model absorbed from the older spec | `tech_doc.md` §4 |
| Support tiers (supported/degraded/refused) vs per-capability levels | per-capability levels + blockers; no global tier | `tech_doc.md` D2 |
| Confidence: five booleans/four caps vs 0.85 cap rules | six booleans `S,M,X,K,R,V` with one function | `tech_doc.md` §12.2 |
| CLI flags: `--attempt-fix`, `--no-fix`, `--keep-stack`, `--service`, `--fast` inconsistencies | one command table; no fix command; no `--keep-env`; no `--allow-egress` | `tech_doc.md` §16.1 |
| k6 version/Python version strings differing across docs | versions live only in `design/12-oss-bom.md` and are re-pinned at P0 | BOM |
| "supports exactly one HTTP service", "GET-only" | multi-service; side-effect classes with write safeguards | `tech_doc.md` §8.4 |
| Entire used as "graph_neighbors only" vs "across product" | Entire = one `CodeIntelAdapter` + partner evidence | `design/13` |
| Replay-based v0/v1 evidence allowed in tests vs "live only" for judging | live only for evidence; recorded data only in unit tests, labelled | `pitch.md`, `design/05` §9 |
| Exit codes 0–8 vs needs-input/blocked | 0–10 | `tech_doc.md` §16.2 |
| Reference app as E2E target and demo | fixtures verify; canaries demonstrate generality; no fixture-specific production logic | `tech_doc.md` §18 |
| Phase plans with hour budgets and `SD-xx` deltas | dependency-ordered phases with gates; SD decisions absorbed | `implementation.md` |
| SD-09 (<4 cores hard fail) vs plug-and-play | kept with explicit override that labels results | `tech_doc.md` §9.6 |

## 2. Reference-project-only decisions removed (audit list)

FastAPI mandatory · PostgreSQL mandatory · exactly one HTTP service · preseeded database with fixed record counts · three-path allowlist · hard-coded endpoints and file locations · planted `F1/F2/D1` as product logic and narrative · fixed investigation path · mandatory PG diagnosis · `.py`-only fix rails · e2e only against the in-repo demo · classifying external repos without executing a test · Compose-only environment · k6 on the host only. Each is replaced by an adapter, a data pack or a policy (see `tech_doc.md` App. D).

## 3. Anti-overfitting audit (run before every milestone demo)

1. `test_no_fixture_leakage` green (names, paths, routes, flaw ids).
2. Metamorphic suite green: renamed routes/files/symbols/ports/tables produce invariant discovery, workloads and diagnosed mechanism.
3. Blind fixtures: oracle sealed before the run (hash committed), authored by someone who did not write the adapters.
4. Held-out canaries untouched: git log of `tests/corpus/heldout/` shows no commits by anyone modifying adapters in the same change.
5. Packs lint: no application identifiers; ≥2 ecosystems per pack or flagged.
6. Grep for literals: no port numbers, route strings, table names or dataset sizes in `loadline/` other than documented constants.
7. Scripted generic policy runs on corpus services without per-service branches.
8. Reports on canaries show *different* operations, services and limitations — not a template.

## 4. Residual technical risks (also tracked in `implementation.md` §5)

| Risk | Severity | Note |
|------|----------|------|
| Kernel-shared containers are not a full boundary | high | tiers, refusal for third-party, honest wording |
| Boot success on unfamiliar repos | high | coverage is a measured quantity; planner loop; named blockers |
| Realistic workloads (bodies, auth, state) | high | smoke gate; harvest; `no_working_operation` |
| Measurement validity on shared/small hosts | high | calibration, saturation verdicts, ceiling labels |
| Agent quality across stacks | medium | structured predictions, discriminating rule, blind fixtures |
| Telemetry coverage for arbitrary runtimes | medium | universal tier + attribution; confidence caps |
| Route extraction accuracy | medium | data packs, runtime corroboration, corpus metrics |
| Fix verification noise | medium | ABBA + CI + effect thresholds + `inconclusive` |
| Scope vs window | high | tiers, cut order, gates |
| Provider data exposure | medium | denylist, redaction, disclosure, local model option |
| AGPL k6 | low | external unmodified process; attribution in submission |

## 5. Things deliberately *not* done

No custom load generator, no model-written load scripts, no automatic merge, no hosted service, no "supports everything" claim, no fixture-specific special cases, no silent fallbacks.
