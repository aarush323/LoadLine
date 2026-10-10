# 07 — Reporting, finding cards, live UI

Mechanics for `tech_doc.md` §14. Section order and tags (measured, projected, hypothesis) are defined there. `V` is false. Remediation is text.

## 1. Artifacts

| Artifact | Status | Generator |
|----------|--------|-----------|
| `report.md` | ship | Jinja2 template over `ReportModel` |
| `report.json` | ship | `ReportModel.model_dump_json()` |
| `ledger.jsonl`, `waves/`, `evidence/` | ship | core |
| `report.html`, share cards | Tier C | later |

One Pydantic `ReportModel`; one render pass for md + json; wording lint runs on the rendered text; render fails on lint violation or recompute mismatch.

## 2. `report.md` skeleton (fixed order; required blocks enforced)

```markdown
# Loadline report — {run_id}
> Verdict: {verdict_headline}     Trace: {neatlogs_link|n/a}

## 1. Verdict
## 2. What was run
## 3. Coverage
## 4. Capacity                  # measured
## 5. Resources and dependencies
## 6. Experiment log
## 7. Projected scale           # projected, with assumptions and a range
## 8. Findings (ranked)
## 9. Ruled out
## 10. Limitations              # never empty
## 11. Reproduce
## 12. Partner artefacts
```

### Deterministic verdict headline templates

- Bracketed: `<mix> sustains **{lo} req/s** with p95 ≤ {slo} ms (SLO source: {source}; confirmed: {yes|no}). Primary limit: **{top_finding_short | not determined}**.`
- Above ladder: `Capacity exceeds the host-measurable ceiling ({cap} req/s); no limit found within it.`
- Below ladder: `Cannot sustain {start} req/s under the SLO on <mix>.`
- Generator/host/invalid: `Capacity not measured: {reason}.`
- Blocked: `Run did not reach measurement: {blocker code} — {what only you can provide}.`

## 3. Finding card

```markdown
### [{severity}] {title} — `{finding_id}`
| Field | Content |
| Confidence | {c} ({band}) — S{✓|✗} M{✓|✗} X{✓|✗} K{✓|✗} R{✓|✗} V{✓|✗} |
| Component / operation | {service}: {operation} |
| Symptom (observed) | {symptom with numbers + evidence ids} |
| Observed facts | bullet list, each with evidence id |
| Hypotheses | bullet list, each with status and the experiment that confirmed/refuted it |
| Mechanism | {statement; causal verbs only if confidence ≥ 0.65} |
| Location / call path | {file:line-range snippets from read_file}; {call path} or `unlocated (reason)` |
| Alternatives considered | {each with outcome} |
| Confirming experiment | {id, prediction, result} — or what would confirm it |
| Remediation | LLD: …  HLD: …  Expected gain: measured {…} or [ESTIMATE] not measured by Loadline |
| Fix status | not attempted / improved / regressed / inconclusive ({ab id}) |
```

Observed facts and hypotheses are never mixed in one list.

## 4. Severity and ranking

See `tech_doc.md` §12.3 for definitions. Assigned in `record_finding` validation, not by the model. Ties: higher confidence, then lexicographic finding id. The top finding supplies the headline's primary-limit clause; if none reaches confidence ≥0.60 the headline says `not determined`.

## 5. Wording lint (`report/lint.py`)

1. Every number has unit and evidence id (same sentence or table row).
2. Rates are `req/s`; percentages ≤1 decimal.
3. Causal verbs (causes, drives, limits) only when finding confidence ≥0.65; else "correlates with/consistent with".
4. Unmeasured gains prefixed `[ESTIMATE]` + "not measured by Loadline" unless a verification step is cited.
5. LLM prose (`executive_summary`, finding text) may contain digits only if present in the `ReportModel` numeric set.
6. Mandatory statements present: isolation tier, trust level, SLO source, stubs (if any), model-provider data note, derived vs user SLO.
7. Forbidden: "obviously/clearly" without a cite; root-cause claims when `limit_attribution` top is generator/host/measurement.
8. No fixture, flaw, or pattern-catalogue identifiers (defensive: report generator never mentions them).

## 6. `report.json` (schema_version 1) — top-level keys

`run`, `repo`, `trust`, `isolation`, `capabilities`, `launch_plan`, `services`, `dependencies`, `data_scale`, `operations[]` (id, class, status, exclusion_reason, provenance), `calibration`, `slo`, `capacity{mix, per_op[]}` (bracket, status, confirmed, steps[]), `telemetry_inventory`, `attributions[]`, `hypotheses[]`, `experiments[]`, `findings[]` (card fields + confidence booleans), `ruled_out[]`, `fix[]` (verification), `limitations[]`, `reproduce`, `partners`, `evidence_index`. Null `lo` ⇒ `"lo": null, "lo_reason": "…"`.

## 7. Live terminal UI

Rich `Live`: phase bar; environment status (tier, services health); current experiment (kind, rate, elapsed); bracket progress; hypotheses table with status; budget meters; last rejection/advice. `--no-live` prints plain lines with timestamps. The UI never prints speculative claims as facts: hypotheses are labelled `hypothesis`.

## 8. Redaction

All report text passes through the secret redactor (pattern + entropy + known-secret set from the run). Tokens, passwords, connection strings, cloud keys are replaced by `‹redacted:kind›`. Code snippets come only from `read_file` ranges after redaction.
