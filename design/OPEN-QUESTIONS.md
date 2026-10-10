# Open questions (v3) — decisions only the humans can make

Defaults apply if nobody answers. None of these changes the contract's generality rules (`tech_doc.md` §0).

| # | Question | Default if silent | Affects |
|---|----------|-------------------|---------|
| 1 | Which model/provider for `LOADLINE_MODEL` (and is a local OpenAI-compatible endpoint acceptable for the demo)? | hosted provider chosen at kickoff | cost, privacy disclosure |
| 2 | Which 4 or 5 corpus repos, and which of them are held out? Pin them before tuning | cover at least two languages and two datastores | acceptance, demo |
| 3 | Which three fixtures' stacks (defaults: Python+PostgreSQL; Node+MongoDB+Redis; polyglot multi-service) and who authors them blind? | defaults; second teammate authors, seals oracle | acceptance |
| 4 | Docker mode on the demo machine: rootless or standard? Does an `--internal` network work (spike S-DOCKER)? | whichever works; limitations printed | demo claim |
| 7 | Default SLO policy (`5×baseline`, clamp 200–2000 ms): acceptable, or should the CLI prompt for an SLO when none is given? | derived default, always printed with its source | usability |
| 8 | Ideas that are not in `tech_doc.md` §0. Do not build them unless that section changes first. | not scheduled | scope |
| 10 | Confirm on Discord: rules say code between 10 Oct start and 12 Oct deadline; event page also lists "Oct 10–11" build window (`hackathon.md`) | plan to the earlier date | schedule |
| 11 | Project/product name final? | Loadline (working) | pitch |
| 12 | Public repo name/org and licence (AGPL implications of k6 are external-process only) | MIT for Loadline, k6 documented as external | submission |

## Answered by the v3 contract (no longer open)

Tool count (seven, `BRIEF.md`) · generator (k6 behind adapter) · support model (per-capability levels) · confidence function (six booleans) · whether FastAPI/Postgres are assumed (no) · whether the reference app may shape logic (no) · whether Docker is a complete boundary (no) · whether fixes merge (never) · whether the agent may write load scripts (no; declarative plans).
