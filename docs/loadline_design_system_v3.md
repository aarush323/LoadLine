# LOADLINE — Design System v3

> **Product feeling:** Anthropic-adjacent editorial warmth × ChatGPT/Codex calm × Cursor's engineering workbench × Sentry's investigative depth.
>
> **Design thesis:** Loadline is a precision instrument with a beautiful surface. It applies controlled pressure, shows where behaviour bends, maps the affected API into real code, and leaves behind a verdict that can be challenged.
>
> **Signature:** warm paper, confident serif headlines, precise modern UI, one dark code-map surface, barely-there glass, and evidence that always outranks decoration.

**This is an original design system, not a pixel clone of Anthropic, ChatGPT, Codex, Cursor, Linear, or Sentry.** It uses open-font alternatives and shared interface principles rather than copying proprietary wordmarks, assets, or exact components.

## 0. The one-line art direction

**A quiet, warm, glass-edged engineering workbench where the code graph is the dark stage and measured pressure is the only thing allowed to shout.**

It must feel expensive without feeling precious; technical without looking like a terminal theme; intelligent without performing “AI”; and beautiful without compromising the trustworthiness of an engineering tool.

The system has three connected surfaces:

| Surface | Job | Character |
|---|---|---|
| **CLI** | Drive the run and narrate state changes | Quiet, compact, tactile, evidence-led |
| **Dashboard** | Explore pressure, code relationships, and experiments | Spacious, editorial, lightly glassed, graph-forward |
| **Markdown report** | Record the final, auditable result | Durable, plain, linkable, honest |

All three render the **same underlying run and evidence model**. The dashboard must not invent a verdict that differs from the CLI or report. The report is not a screenshot of the dashboard; it is the canonical written result.

> **Scope guard:** the MVP currently commits to `report.md` and `report.json`, not a served dashboard. This design defines the dashboard direction, but implementation is a scope change: update `tech_doc.md` first, then align `implementation.md` and this spec. Do not quietly add a web server to the MVP.

---

## 1. Reference study: what to borrow, what not to copy

### 1.1 Claude / Anthropic — editorial warmth and confidence

Borrow the feeling of readable long-form typography, warm neutrals, generous whitespace, and a headline that sounds like a clear conclusion rather than a status widget. Use a distinctive serif in the right places; let technical content remain precise and practical.

**Loadline translation:** a serif display headline such as “The system bends at 146 req/s.” The result feels authored and composed; the surrounding interface remains a compact engineering product.

**Do not:** use Anthropic's logo, proprietary typefaces, exact proprietary components, or Claude-specific iconography. The chosen Loadline type system uses readily available alternatives.

Reference: [Claude / Anthropic](https://claude.com/), [Claude design-system guidance](https://support.claude.com/en/articles/14604397-set-up-your-design-system-in-claude-design).

### 1.2 ChatGPT / Codex — calm product UI

Borrow restraint: an uncluttered workspace, concise controls, clear task state, familiar system behaviour, and accent colour reserved for meaningful actions. Avoid gratuitous gradients, rainbow cards, and a different visual treatment for every feature.

**Loadline translation:** simple surfaces, a discreet run switcher, compact primary actions, low-noise navigation, and shared components across Overview, Code map, Experiments, Evidence, and Environment.

**Do not:** reproduce ChatGPT or Codex layouts exactly, use their marks, or make the interface resemble a conversation product. Loadline is an investigation workspace, not a chat wrapper.

Reference: [OpenAI design guidelines](https://openai.com/brand/), [OpenAI UI guidelines](https://developers.openai.com/plugins/concepts/ui-guidelines).

### 1.3 Cursor — the developer workbench

Borrow a strong sense of place: focused work areas, consistent component tokens, clear task progress, keyboard-first navigation, and tools that make a codebase feel navigable rather than abstract.

**Loadline translation:** a persistent repository/run context, command palette, keyboard shortcuts, selected API → code relationships, and an inspector that never loses the selected run.

**Do not:** turn the product into an IDE clone, add a file explorer just to look technical, or use neon accents across every panel.

Reference: [Cursor](https://cursor.com/), [Cursor design-system rules](https://prod.cursor.com/for/designers).

### 1.4 Sentry — investigation depth

Borrow the path from symptom to details to source. A slow endpoint should resolve into measurements, related spans or telemetry, source locations, and a carefully qualified explanation.

**Loadline translation:** every finding has evidence anchors; graph nodes open a provenance-aware inspector; “open source” and “open evidence” are first-class actions.

Reference: [Sentry](https://sentry.io/).

### 1.5 Entire Graph — a real map, not a drawn architecture

Entire Graph can provide definitions, callers/callees, supported route relationships, change-impact information, source locations, and graph exports. Its own documentation also surfaces coverage, unsupported areas, warnings, and heuristic relations.

**Loadline translation:** use graph structure to orient and explore the repository; overlay measured runtime pressure only where a specific operation can be linked to a code node. Static relationships remain static. Unknown relationships remain unknown.

**Do not:** imply that every edge is a runtime trace, infer causality from adjacency, or hide partial graph coverage.

Reference: [Entire Graph repository and documentation](https://github.com/entireio/entire-graph).

### 1.6 k6 — make measurements legible

Use k6's measured data and threshold verdicts as the source for load metrics. The overview should show request duration distributions, failures, throughput, offered load, and threshold lines. Time-series data should retain timestamps and traceable samples when the selected output supports it.

Reference: [k6 metrics](https://grafana.com/docs/k6/latest/using-k6/metrics/), [k6 thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/), [k6 result output](https://grafana.com/docs/k6/latest/get-started/results-output/).

### Synthesis

**Editorial type + minimalist product chrome + a developer-grade graph + measured performance data.** That is Loadline. It should not look like four references pasted together. The common denominator is calm hierarchy: one clear headline, a few numbers that matter, one dominant graph, and evidence one click away.

---

## 2. Non-negotiable design principles

### P01 — Evidence over theatre

Every number, state, and highlight must come from the run ledger or an explicitly labelled derivation. No fabricated live logs, fake agent typing, made-up “AI confidence” gauges, animated pulse that implies real activity, or ornamental dashboard metrics.

### P02 — One focal point per screen

On Overview, the focal point is the measured capacity edge and pressure timeline. On Code map, it is the graph. On Experiments, it is the prediction-versus-observation comparison. On the final report, it is the conclusion with its evidence. Do not make every region compete for attention.

### P03 — Calm until there is a reason not to be

The interface uses neutral ink, warm surfaces, hairline borders, and one signal colour. A measured SLO breach may be vivid. A hypothesis should be quiet. A successfully completed run should not turn the entire page green.

### P04 — Glass is a material, not a theme

Use glass only to establish a floating layer: the global command bar, sticky workspace header, popover, command palette, or a contextual drawer. The graph canvas, chart plot, tables, and report body should remain solid and crisp. Frosting every card produces fog, weakens contrast, and makes the UI feel cheap.

### P05 — Real graph, clear semantics

Every node and edge carries a type, stable identity, and provenance. Graph topology comes from Entire Graph output; pressure comes from measured operation mapping; hypotheses are agent-authored conjectures. Separate these visually and semantically.

### P06 — Unknown is a valid state

Use “Not measured”, “Not mapped”, “Coverage incomplete”, “Inconclusive”, or `investigation_incomplete` as appropriate. Never fill a gap with a plausible-looking number. Missing coverage must be visible without dominating the page.

### P07 — Density is progressive

Overview answers the main question in under five seconds. Advanced details sit one level deeper in the inspector, experiment details, or evidence ledger. Use disclosure rather than shrinking all text until it fits.

### P08 — One source of truth

CLI, dashboard, Markdown, and JSON share the same run ID, operation IDs, evidence IDs, experiment IDs, verdicts, units, and timestamps. UI components must not re-compute a competing interpretation.

### P09 — No mystery meat controls

Every icon-only button has a tooltip and accessible name. Use familiar actions (`Open source`, `View evidence`, `Copy run ID`), not symbolic controls that require guessing.

### P10 — Product before decoration

If removing an effect makes the interface clearer without losing information, remove it. No ambient particle fields, fake scanlines, rainbow gradients, animated noise, massive ASCII mascots, or permanently oscillating graph nodes.

---

## 3. Brand identity

### 3.1 Wordmark

Use lowercase **`loadline`** as the primary wordmark. Typography should feel compact, calm, and slightly technical. Avoid over-tight tracking or a futuristic sci-fi font.

### 3.2 Signal mark

The mark is a baseline interrupted by a pressure curve. Its shape should be simple enough to render in a terminal and precise enough to work as a small SVG.

```text
loadline   ─────╱╲────
```

The curve must not be treated as a performance graph unless it is tied to real measurements. As a logo it is a stable brand mark; in charts it represents actual data.

### 3.3 Logo construction

- SVG mark: 24 × 24 px for app navigation; 16 × 16 px for compact contexts.
- Stroke: 1.6 px at 24 px size; round joins and caps.
- Wordmark: lowercase, medium weight, 0 to -0.025em letter spacing.
- Clear space: at least half the mark's width around the lockup.
- On dark backgrounds, use the warm white mark. On light backgrounds, use ink with the signal accent only on the endpoint.
- Never put the logo inside an app tile gradient, enclosing circle, or fake terminal window.

### 3.4 Voice

Loadline talks like a careful performance engineer, not a hype deck.

| Prefer | Avoid |
|---|---|
| “p95 crossed the 500 ms SLO at 146 req/s.” | “Your app is melting.” |
| “Prediction not supported by this experiment.” | “The agent found the root cause!” |
| “No bottleneck found within the measured range.” | “Your app is healthy.” |
| “Not measured: host telemetry unavailable.” | A plausible value or empty gap |
| “Investigations stopped: experiment budget exhausted.” | “The AI got stuck.” |

The product may be warm and human, but not jokey during an incident. Never claim to have fixed, confirmed, or diagnosed something beyond the evidence.

---

## 4. Typography system

The type system intentionally contrasts a warm editorial display face with a modern software UI and a high-legibility mono. It captures the *cadence* of editorial AI products without using their proprietary fonts.

### 4.1 Font families

| Token | Preferred stack | Usage |
|---|---|---|
| `font-display` | `Instrument Serif`, `Georgia`, serif | The main conclusion headline, report title, rare editorial statements |
| `font-ui` | `Geist`, `DM Sans`, `Inter`, system sans-serif | Navigation, body text, controls, table labels, descriptions |
| `font-mono` | `Geist Mono`, `IBM Plex Mono`, `ui-monospace`, monospace | Numbers, paths, IDs, code, graph labels, event timestamps |

Recommended web import for the prototype and future UI (self-hosting is optional; follow the project’s privacy/network constraints):

```css
@import url('https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400..600&family=Geist:wght@400..700&family=Instrument+Serif:ital@0;1&display=swap');
```

If a chosen font fails to load, preserve hierarchy through the declared fallback stack. The layout must remain usable with network fonts disabled. Do not package or distribute proprietary typefaces.

### 4.2 Type scale

Desktop baseline, with responsive reduction on narrow screens:

| Token | Size / line height | Weight | Use |
|---|---:|---:|---|
| `display-xl` | 44 / 1.04 | 400 | Main conclusion headline only |
| `display-lg` | 34 / 1.08 | 400 | Page-level title |
| `heading-1` | 24 / 1.25 | 500–600 | Major section |
| `heading-2` | 17 / 1.35 | 550–600 | Panel or finding title |
| `body-lg` | 15 / 1.65 | 400 | Explanatory paragraph |
| `body` | 14 / 1.55 | 400 | Main UI copy |
| `body-sm` | 12.5 / 1.5 | 400–500 | Supporting context and tables |
| `label` | 10.5 / 1.4 | 550–650 | Provenance, status, section eyebrow |
| `mono-lg` | 20 / 1.2 | 450–500 | Hero metrics |
| `mono` | 12 / 1.5 | 400–500 | Code, IDs, chart values |
| `mono-sm` | 10.5 / 1.45 | 400 | Dense technical metadata only |

### 4.3 Typography rules

- The serif is a **punctuation mark**, not the entire interface. Use it for one conclusion headline and rare report titles. Do not style every section title as editorial.
- Use `font-variant-numeric: tabular-nums` for values that change or align in columns.
- Keep labels sentence-case except compact provenance tags (`MEASURED`, `STATIC`, `SOURCE`) where uppercase improves scanning.
- Avoid letter-spaced all-caps prose.
- Avoid overly bold body copy. Reserve 600+ weights for labels, selected controls, and short findings.
- Never use a display face in code, numbers, axes, or the graph.
- Do not truncate critical source paths without a hover/click way to inspect and copy the full path.

---

## 5. Colour and semantic tokens

The canonical dashboard is **warm light mode with a dark graph stage**. A full dark theme can be added later without changing semantic colours. Keep the palette narrow. Most UI is neutral; colours describe evidence states.

### 5.1 Core light palette

| Token | Hex | Purpose |
|---|---|---|
| `canvas` | `#F6F5F0` | App background, warm near-white |
| `canvas-top` | `#FBFAF7` | Top workspace wash, almost imperceptible |
| `surface` | `#FFFFFF` | Solid main panel surface |
| `surface-raised` | `#FEFDFB` | Dialog and popover base |
| `surface-soft` | `#F0EFE9` | Selected row, quiet grouping, filter strip |
| `surface-inset` | `#E8E7DF` | Recessed controls or secondary areas |
| `ink` | `#20211E` | Primary text |
| `ink-soft` | `#454741` | Secondary headings and body |
| `muted` | `#777970` | Metadata, helper text |
| `muted-2` | `#96978E` | Tertiary metadata; not body text |
| `rule` | `#E2E1D9` | Standard hairline divider |
| `rule-strong` | `#D2D1C8` | Active boundary / table header |
| `brand` | `#B96648` | Rust/copper identity accent |
| `brand-soft` | `#F4E7E0` | Very light selected brand background |
| `pressure` | `#C84738` | Measured SLO breach, failed operation |
| `pressure-soft` | `#FBECE8` | Measured failure highlight |
| `healthy` | `#38785F` | Explicit pass verdict only |
| `healthy-soft` | `#EAF3EE` | Passing status background |
| `hypothesis` | `#8872B5` | Hypothesis-only elements |
| `hypothesis-soft` | `#F1EDF8` | Hypothesis label background |
| `info` | `#4E6E8A` | Neutral provenance/context |
| `focus` | `#5C7462` | Focus ring / keyboard navigation |

### 5.2 Dark graph palette

| Token | Hex | Use |
|---|---|---|
| `graph-bg` | `#171A18` | Graph stage |
| `graph-surface` | `#1F2320` | Graph node / floating mini panel |
| `graph-grid` | `#292E2A` | Subtle grid |
| `graph-line` | `#4B514B` | Static relationship edges |
| `graph-ink` | `#F0F0E9` | Primary graph labels |
| `graph-muted` | `#A2A79E` | Secondary labels |
| `graph-accent` | `#C7E6A3` | Selected node outline / selected path |
| `graph-pressure` | `#FF806C` | Measured pressure overlay |
| `graph-hypothesis` | `#C0A6FF` | Hypothesis path only |

### 5.3 Colour semantics

- **Rust (`brand`)** identifies Loadline, a currently selected primary action, or a branded graphic. It is not a severity colour.
- **Coral/red (`pressure`)** means a measured threshold breach, measured failure, or explicit error. Never apply it because a model thinks something “looks suspicious.”
- **Green (`healthy`)** appears only for an explicit passing verdict.
- **Violet (`hypothesis`)** marks a hypothesis or unconfirmed path. It must never be used to depict measured performance.
- **Gray (`muted`)** means secondary context, not failure.
- **No colour alone may carry meaning.** Include text labels, symbols, line style, or shape differences.

### 5.4 Chart colour rules

- Offered load: ink / graphite line.
- Measured latency: brand rust line or strong neutral line; reserve pressure red for the segment/event that actually breaches the SLO.
- Error rate: neutral when passing; pressure colour only when the measured threshold fails.
- SLO: dashed line with a visible numeric label.
- Projected data: dashed line plus explicit `PROJECTED` key. Never connect measured and projected points with one continuous solid line.
- Hypothesis markers: violet marker, clearly separate from the measurement series.
- Limit visible simultaneous series to 3–4. Prefer focused toggles over rainbow legends.

---

## 6. Glassmorphism system

### 6.1 The intended feel

Glass is an edge treatment for **floating context**, not a blanket blur effect. It should feel like a thin pane sitting above warm paper: slightly translucent, softly bounded, and easy to read. A user should notice the composition, not think “glassmorphism!”

### 6.2 Approved glass surfaces

1. **Workspace top bar:** sticky, lightly translucent, backdrop blur.
2. **Global command palette (`⌘K` / `Ctrl+K`):** stronger blur, solid-enough fill, elevated shadow.
3. **Popover / filter menu:** light glass with crisp border.
4. **Floating graph inspector or tooltip:** only when it overlays the graph and never obscures key nodes.
5. **Toast:** opaque enough for WCAG contrast and dismissible or time-limited without losing essential information.

### 6.3 Surfaces that stay solid

- Chart plot region and chart labels.
- Graph canvas and graph nodes.
- Operation table and evidence ledger.
- Finding descriptions and report content.
- Status messages with critical failure/blocker information.

### 6.4 Glass tokens

```css
:root {
  --glass-bg: rgba(251, 250, 247, 0.76);
  --glass-bg-strong: rgba(255, 255, 255, 0.88);
  --glass-border: rgba(55, 54, 47, 0.09);
  --glass-highlight: rgba(255, 255, 255, 0.80);
  --glass-blur: 18px;
  --glass-saturate: 125%;
  --glass-shadow: 0 8px 28px rgba(30, 29, 24, 0.055), 0 1px 2px rgba(30, 29, 24, 0.035);
}

.glass-surface {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow), inset 0 1px 0 var(--glass-highlight);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}
```

When `backdrop-filter` is unsupported, the declared background is already opaque enough to remain legible. The product must not require blur to show boundaries, text, or state.

### 6.5 Glass anti-patterns

No bright white neon outline; no rainbow/iridescent blobs; no thick frosted panels behind paragraphs; no 40 px blur; no nested glass panels inside other glass panels; no glass graph nodes; no bright gradients through text; no shadows that make each card float independently. One or two glass layers per viewport is usually enough.

---

## 7. Layout, grid, and spacing

### 7.1 Base grid

- Base spacing increment: **4 px**; major layout uses 8 px increments.
- Desktop sidebar: 224–244 px; optional compact mode: 68 px.
- Header height: 56–64 px.
- Main content max width: 1440 px; page gutters 28–40 px on large screens.
- Panel inner padding: 16–22 px; major section gaps: 28–36 px.
- Graph work area: 2.0:1 to 2.3:1 map-to-inspector split on wide screens; stack inspector below graph when less than 980 px.
- Table row: 52–60 px on desktop; preserve touch-safe interactive areas on mobile.

### 7.2 Radii

| Token | Value | Use |
|---|---:|---|
| `radius-xs` | 4 px | Inline chips, code tags |
| `radius-sm` | 7 px | Inputs, buttons, small panels |
| `radius-md` | 11 px | Main data panels |
| `radius-lg` | 16 px | Command palette, large workspace panes |
| `radius-pill` | 999 px | Small status dot + label only, not generic buttons |

Do not radius every element to 16–24 px. A little geometry and a little softness is the balance.

### 7.3 Borders and shadows

- Default separation is a 1 px neutral border.
- Use a shadow only where elevation creates real hierarchy: command palette, dropdown, overlay, or floating inspector.
- Static cards should not use shadow by default.
- Focus uses a 2 px outline or offset ring, not a shadow-only cue.

### 7.4 Main application frame

- Sidebar and sticky topbar are lightly glassed.
- Main reading canvas is warm and quiet.
- Main page is continuous; do not wrap every section inside a card.
- Section headings sit above content with a short explanatory line and an optional right-side action.
- Run ID, commit SHA, and repository stay discoverable in one persistent context area.

---

## 8. Dashboard information architecture

The dashboard should be a **single-run investigation workspace**, not fleet monitoring software. Do not add multiple-repo analytics, saved dashboards, team management, or general chat unless separately approved.

### 8.1 Navigation

Exactly five destinations:

1. **Overview** — run outcome, capacity edge, key time series, most pressured operations, latest supported finding.
2. **Code map** — Entire Graph structure overlaid with only defensible operation pressure and findings.
3. **Experiments** — predictions, experiment conditions, measurements, scored outcomes.
4. **Evidence** — filterable traceable evidence ledger.
5. **Environment** — detected services, sandbox policy, resource constraints, telemetry/graph coverage, limitations.

Use a quiet icon and text label. Active selection gets a soft surface and a 2 px left-edge indicator or icon tint. Do not put a large coloured badge on every destination. If a destination has a count, show it only when it conveys actionable information (for example, unmapped endpoints).

### 8.2 Global workspace header

Persistent, thin, optionally sticky. Contains:

- Breadcrumb: `RUNS / CHECKOUT-API / OVERVIEW`.
- Repository and branch/commit context (short SHA with copy action).
- Run state (`RUNNING`, `COMPLETE`, `BLOCKED`, `INVESTIGATION INCOMPLETE`).
- Evidence/report actions (`report.md`, `report.json`).
- Command palette shortcut.

Do not render a full navigation bar with giant app branding and several competing buttons. Header should give context and then get out of the way.

### 8.3 Overview hierarchy

**A. Conclusion hero**

Example: “The system bends at 146 req/s.” The number is based on the first measured SLO-breaching load step, not a fitted theoretical capacity. Under it, state the passing load, SLO, workload profile, and whether the observation is measured or projected.

**B. Four compact metric cells**

1. Peak passing offered load.
2. p95 latency at the last passing load.
3. Error rate at first failing step.
4. Investigation status (confirmed / inconclusive / incomplete count).

These are not four colourful cards. Use one continuous horizontal strip with hairline separators. Every number has a unit and a label; hover/focus may reveal the evidence ID.

**C. Shared-time pressure chart**

Use two aligned plots sharing the same x-axis: offered load (req/s) above, p95 latency (ms) below. Show phase bands for baseline, ramp, and investigator experiments only when those phases occurred. The latency plot includes the actual SLO line and a marker at the first breach. This is more honest than overlaying req/s and milliseconds on one y-axis.

**D. Where pressure lands**

A wide graph canvas with the selected operation, related handlers/functions, dependency nodes, and a compact inspector. This is Loadline's signature panel. It should be the visual anchor of the dashboard.

**E. HTTP operations table**

Only operations actually loaded after safety checks appear in the loaded set. Include method, route, source mapping status, p95, error rate, achieved rate, SLO verdict, and evidence/source links. Make the whole row keyboard-accessible and clickable.

**F. Investigation trail**

A short sequence of material events. Default to a few events that change the investigation: prediction proposed, experiment accepted/rejected, outcome code-scored, finding written, budget/stall blocker. The full chronological stream lives in Experiments/Evidence.

### 8.4 Avoid dashboard noise

- No giant circular speedometer.
- No composite “health score”.
- No empty chart frames if there is no data. Show “Not measured” plus the reason.
- No all-green success panel.
- No arbitrary chart-card grid.
- No “AI reasoning” chat window beside the graph.
- No duplicated table and card summarizing the same value without a reason.

---

## 9. Entire Graph visual semantics

This is the main differentiator. The graph should show **what the loaded operation maps to in code**, not a fictional runtime trace.

### 9.1 Node types

| Entity | Shape | Label detail |
|---|---|---|
| HTTP operation | rounded rectangle | `GET /api/orders` + measured status/metric |
| Route / controller | rounded rectangle | symbol + file:line |
| Function / method | rectangle | symbol name + language/module |
| Database operation / query layer | pill or compact rectangle | adapter-provided operation label; no guessed query text |
| Data model / table / collection | cylinder or database glyph | name only when discovered through evidence |
| External/dependency service | hexagon or outlined rounded rectangle | discovered service name |
| Hypothesis | dashed outline card | short hypothesis ID and phrase, not a code entity |

Use shape plus labels to encode types; colour does not uniquely encode node type. Do not put invented table names or generic “database” entities if the graph does not supply them.

### 9.2 Edge grammar

| Edge | Rendering | Meaning |
|---|---|---|
| Static relationship from Entire Graph | thin solid muted line | Graph says a relationship exists |
| Selected code path | stronger line + selected outline | Traversal/relationship chosen in the UI, not runtime timing |
| Runtime evidence link | small solid signal anchor with evidence ID | Measured evidence is associated with an operation/node mapping |
| Hypothesis path | violet dashed line | Proposed explanation, not established fact |
| Unknown/unresolved relation | omitted or explicit unresolved marker | Do not draw an inferred connector to make the picture complete |

Legend is always visible or one click away. The selected path must remain distinct from measured pressure. A source relationship never means the edge itself was timed.

### 9.3 Pressure overlay

- A measured operation can have a coral outline and a compact `p95 812 ms` label.
- The next node only receives a pressure state if the mapping between the operation and that node is supported. Otherwise, keep node neutral and explain the mapping status.
- A violet hypothesis path can cross static graph edges, but it should remain dashed and be labelled “hypothesis”.
- A line thickness should not imply latency unless its scale and meaning are documented. Prefer colour + endpoint marker to arbitrary edge thickness.

### 9.4 Graph interactions

1. Select node → inspector changes.
2. Inspector shows symbol, file:line, relationship provenance/confidence, graph revision, related operation IDs, runtime metrics where available, and evidence IDs.
3. `Open source` opens the exact source location if the environment supports it; otherwise `Copy file:line` is always available.
4. `View evidence` filters ledger to the relevant evidence IDs.
5. `Trace callers` / `Trace callees` invokes or displays actual graph relationships only.
6. Zoom, pan, fit, clear selection. Keep reset/fit and graph legend visible.
7. Search highlights matches; it must not create nodes that were not in the graph.

### 9.5 Large graph handling

Do not dump a repository-wide “hairball” into the main screen. The default view is a **focused neighbourhood** around the selected HTTP operation or finding. Expand on demand. Preserve stable identifiers when changing depth. Show the result count and any truncation/coverage boundary explicitly.

### 9.6 Provenance fields

Each visualized relation should have a record equivalent to:

```json
{
  "source_id": "graph:relation:...",
  "source_kind": "entire_graph",
  "relation_kind": "calls",
  "from_symbol": "...",
  "to_symbol": "...",
  "file_locations": ["src/orders/service.py:84"],
  "confidence": "reported_by_provider",
  "runtime_timing": "not_measured"
}
```

This schema is conceptual, not a mandate for exact current field names. UI labels should be derived from real provider data. If the provider has no confidence field or cannot resolve a location, say so rather than manufacturing a confidence score.

---

## 10. Charts and measurement visualisation

### 10.1 Every chart answers one question

- **Load vs latency:** at what offered load did latency change or cross the SLO?
- **Throughput vs errors:** did served throughput flatten while failure rate rose?
- **Resource telemetry:** did an observed resource limit coincide with the performance event?
- **Experiment comparison:** did the result match the prediction's discriminator?

If a visual doesn't answer a question or support an investigation, cut it.

### 10.2 Required chart rules

- Always show axis labels and units.
- Use real time or load-step x-values; no smoothed animation that hides the sampled points.
- Include actual threshold values in the legend or on the plot.
- Hover/focus shows timestamp, sample value, phase, evidence ID, and series.
- Distinguish missing intervals from zero values.
- Show phase boundaries when baseline/ramp/experiment phases are real and timestamped.
- Use subtle gridlines. Gridlines should be quieter than lines/data points.
- Avoid chartjunk: 3D, shiny gradients, outer glow, radial gauges, and excessive tick labels.
- For a small screen, simplify ticks before hiding units or threshold context.

### 10.3 Do not place req/s and milliseconds on one unlabeled axis

Preferred: two vertically stacked plots sharing the same x-axis. If separate scales are truly necessary in a compact variant, clearly label both axes and avoid implying that the line magnitudes are comparable.

### 10.4 Measured, projected, hypothesis

The report and dashboard must keep the three classes separate:

- **MEASURED:** directly observed in this run; solid line/marker.
- **PROJECTED:** extrapolated by a disclosed method; dashed line and `PROJECTED` label.
- **HYPOTHESIS:** an unconfirmed explanation/prediction; violet dashed annotation, never a time-series value.

There is no visual state that blurs these into a single “confidence” line. Do not fit or show USL capacity curves in the MVP, which explicitly excludes USL fit.

---

## 11. Metric strip, status, and operation table

### 11.1 Metric strip

Use a continuous surface, not a set of four colourful cards. Each cell contains: label → prominent monospaced value + unit → short context → evidence anchor. The first/critical metric may use brand emphasis; breached values use pressure semantics.

### 11.2 Verdict grammar

- `PASSING` — text + green/neutral pass glyph.
- `BREACHED` — text + coral marker.
- `BLOCKED` — text + explicit reason.
- `INCONCLUSIVE` — text + reason or unresolved prediction.
- `INVESTIGATION INCOMPLETE` — text + the stopping condition.
- `NOT MEASURED` — neutral text + reason.

Do not use “healthy” to describe an entire app from a single test. Prefer the actual SLO/verdict.

### 11.3 Operation table

Columns on desktop:

`METHOD + ROUTE` · `SOURCE MAP` · `p95` · `ERROR RATE` · `ACHIEVED RATE` · `SLO` · `EVIDENCE`

- Align numbers by decimal/tabular figures.
- Keep method tag low contrast; GET should not be a green pill by default.
- The active row gets a pale warm tint and a narrow leading line, not a saturated fill.
- Show `Source not mapped` honestly.
- Sortable headers must include an accessible name and visible sort state.
- On mobile, collapse secondary columns behind a row disclosure rather than horizontal-scrolling an unreadable table.

---

## 12. Investigator / experiment UI

The investigator should be presented as a controlled scientific process, not a talking chatbot.

### 12.1 The canonical chain

**Hypothesis → structured prediction → experiment → observation → code-scored verdict → finding.**

Each step gets an ID and visible relationship to the next. If one step is absent, the UI states what is missing; it doesn't draw a completed chain as decoration.

### 12.2 Hypothesis row

Each hypothesis includes:

- `H-02` plus a short neutral title.
- Current status (`PROPOSED`, `TESTING`, `SUPPORTED`, `NOT SUPPORTED`, `INCONCLUSIVE`).
- Prediction expressed in observable terms.
- What result would discriminate it from a plausible alternative.
- Linked experiment IDs.
- The code-scored decision and associated evidence IDs.

Do not show a model's free-form confidence such as “92% sure” unless that quantity is produced by a documented, calibrated method and approved in product scope.

### 12.3 Experiment detail

Use a simple vertical timeline with four distinct stages: plan, validation, execution, evaluation. Rejected experiments are first-class events, not errors to hide. Show why they were rejected (e.g. unsafe operation, invalid plan, resource budget, invalid step), and link to neatlogs evidence.

### 12.4 Status colour

Hypothesis state uses status text and shape first. Violet marks conjecture; green only appears for a supported/confirmed result as defined by code. A stopped budget is neutral/incomplete, not red unless there was a measured failure.

---

## 13. CLI design language

The CLI should feel like the dashboard compressed into a terminal. Use the same words, order, and evidence identities. Keep the visual mark small.

### 13.1 Starting screen

```text
loadline  ─────╱╲────

run   checkout-api · 8a4bf71
      ─────────────────────────────────────────
      inspect   isolate   load   investigate   report
```

Do not print a large multi-line ASCII logo on every invocation. `loadline --version` and non-TTY runs should be compact.

### 13.2 Stage presentation

Each stage has one row with current state and a meaningful description:

```text
✓ inspect       12 services/operations resolved   0.8s
✓ isolate       egress denial verified             3.1s
✓ load          120 req/s passing · SLO at 146     42s
◉ investigate   EXP-03 running · prediction P-03
· report        waiting for evidence ledger
```

The numbers above are illustrative examples only. Production CLI output is populated from actual events. No hard-coded timings or counts.

### 13.3 Event grammar

Use a small, consistent grammar:

```text
<symbol> <stage> <verb phrase>  [state / quantitative evidence]
```

Examples:

```text
✓ workload    GET /api/orders passed read-safe smoke check
! experiment  EXP-04 rejected: target operation is not read-safe
→ prediction  P-03 expects DB span p95 to rise before API p95
✓ evaluation  P-03 not supported · EV-031
! run         investigation_incomplete: experiment budget exhausted
```

A real status indicator is acceptable; a fake spinner that keeps spinning while nothing runs is not. A single updating spinner is permissible for a known in-progress process in an interactive TTY; it must stop/update from actual process state and be disabled in CI output.

### 13.4 Colour in terminal

- Primary text default terminal foreground.
- Secondary information dim, but still readable.
- Brand colour on the logo and current stage.
- Red only for a measured breach, actual failure, or blocker.
- Violet only for hypothesis state.
- Respect `NO_COLOR`, non-TTY, and terminal capabilities.
- Avoid forced bright ANSI green output for every passing line.

### 13.5 CLI ending

End with a durable outcome, not a celebratory animation:

```text
RESULT  report ready
        Measured SLO boundary: 120 req/s passes; 146 req/s breaches.
        Finding F-01 links to EV-021, EXP-03 and src/orders/service.py:84.
        Wrote report.md and report.json
```

Or:

```text
RESULT  blocked: no safe HTTP operation could be smoke-tested
        See report.md for the blocker and observed environment.
```

Never show a success outcome if the investigation is incomplete or the report generation failed.

---

## 14. Logs and event feed

### 14.1 Event anatomy

Every material event should expose:

- Relative/absolute timestamp as useful to the current view.
- Stage.
- Event type.
- Short human phrase.
- Result/state.
- Evidence IDs or experiment ID when they exist.
- Details affordance for raw structured payload.

### 14.2 Information order

1. What happened.
2. What changed or what decision was made.
3. Why that decision was made.
4. Where the supporting evidence is.

Do not dump a raw JSON blob by default. Do not replace details with vague status icons. Event payloads remain available for debugging.

### 14.3 Useful event types

- `service_discovered`
- `operation_proposed`
- `operation_smoke_passed` / `operation_smoke_rejected`
- `sandbox_constraint_applied`
- `egress_denial_verified`
- `load_step_completed`
- `threshold_breached`
- `hypothesis_created`
- `experiment_rejected` / `experiment_started` / `experiment_completed`
- `prediction_scored`
- `finding_written`
- `investigation_stopped`
- `report_written`
- `teardown_verified`

Only emit events the implementation actually models. These are vocabulary examples, not instructions to fabricate an event for every phase.

---

## 15. Markdown report design

The Markdown report should feel like a sharply edited technical memo. Keep the HTML dashboard styling out of the content. It should render well on GitHub, VS Code, terminal Markdown readers, and a plain-text copy.

### 15.1 Report hierarchy

```markdown
# Loadline report — checkout-api

**Outcome:** SLO boundary observed at 120 req/s passing / 146 req/s breaching
**Run:** `LL-7F2C` · **Commit:** `8a4bf71` · **Date:** …

## Executive result
One concise paragraph. Name the measured boundary and the limiting scope.

## Measured capacity
| Offered load | p95 | Error rate | SLO |
|---:|---:|---:|---|

## Findings
### F-01 — Repeated order reads may amplify tail latency
**Verdict:** Supported by EXP-03
**Evidence:** EV-021, EV-028
**Code:** `src/orders/service.py:84`

## Experiments
## Coverage and environment
## Limitations
## Reproduction
```

Values above are placeholders to illustrate layout. Real reports use ledger values only.

### 15.2 Evidence links

Every material metric and conclusion must link or name its evidence ID. Use stable IDs (`EV-021`, `EXP-03`, `F-01`) so the dashboard can deep-link back into the same record. Preserve exact source paths and commit SHA.

### 15.3 Embedded charts

If report assets are permitted by the implementation contract, write a chart as a separate SVG/PNG file and link it from Markdown. Treat it as a generated artifact derived from the ledger. If no asset is produced, include the data table and textual description instead; do not create a fake graph or require `report.html`.

### 15.4 Evidence classes

Render labels verbatim and consistently:

- **[MEASURED]** direct observation in this run.
- **[PROJECTED]** an estimate outside the directly observed range, plus disclosed method/assumptions.
- **[HYPOTHESIS]** an unconfirmed explanation or prediction.

These labels are semantic contracts, not just badges. Do not put a projected capacity number under a measured heading. The report must include **Limitations**, including what wasn't tested or measured, host saturation/emulation constraints, graph mapping gaps, and why the run stopped if incomplete.

### 15.5 Outcomes are designed states

All are valid:

- `report.md` with an evidence-backed finding.
- “No bottleneck found within the measured range.”
- `blocked: <specific reason>`.
- `investigation_incomplete: <specific stopping condition>`.

Do not visually frame incomplete or blocked output as a successful diagnosis.

---

## 16. Core components

### 16.1 Buttons

- Primary: dark ink fill, white text, quiet hover; one primary action per local region.
- Secondary: transparent/solid warm surface, 1 px border.
- Tertiary: text action; avoid link-blue unless linking outside the product.
- Destructive: pressure red only for an actual destructive/critical action, not for ordinary navigation.
- Focus-visible: 2 px `focus` ring with 2 px offset.
- Disabled actions explain why when the reason is not obvious.

### 16.2 Inputs and command palette

- 40–44 px control height.
- Light border by default; stronger border on focus.
- No oversized pill inputs.
- Command palette width 560–680 px desktop, max viewport width minus 24 px on mobile.
- Search row plus grouped results, shortcut hints, and a selected result line.
- Open with `⌘K` on macOS and `Ctrl+K` elsewhere; Escape closes; arrow keys navigate; Enter activates.
- Search result labels indicate destination/context (`Code map · GET /api/orders`).

### 16.3 Cards/panels

Panels use a white solid surface, one quiet border, and 11 px radius. Cards should not all cast shadows. Group adjacent values with dividers before inventing another card.

### 16.4 Chips / tags

Use chips for semantic states and brief provenance. Sentence-case is the default. Keep tags short; no emoji. Never put a colored badge in front of every heading. Colour is only used for meaningful state classes.

### 16.5 Tooltips

- Delay: 250–400 ms.
- Simple dark/ink surface with white text, 12 px copy, 6 px radius.
- Use for icon-only controls and abbreviated metadata.
- Do not put essential warnings only in a tooltip.

### 16.6 Toasts

- Bottom-center or bottom-right, not both.
- 2–4 seconds for reversible confirmation (e.g. copied run ID).
- Persistent inline state for blockers and errors; do not rely on a toast for a critical failure.
- No success sound or celebratory motion.

### 16.7 Empty states

Empty states explain the reason and the next meaningful step. Use a small mark or line illustration only when helpful. Do not fill an empty chart with a fake dataset. Example: `No read-safe operation passed smoke testing. No load was generated.`

---

## 17. Motion and interaction quality

- Standard transition: 140–180 ms, `cubic-bezier(.2, .7, .2, 1)`.
- Modal/palette entrance: 180–220 ms opacity + 4–6 px rise; no dramatic zoom.
- Row hover: 100–140 ms background tint.
- Graph selection: 120–180 ms line/outline emphasis; no node bouncing.
- Time-series update: add measured points at their timestamp; do not interpolate in a misleading way.
- Loading indication is tied to actual run stage or request state.
- `prefers-reduced-motion: reduce` disables non-essential movement and smooth scrolling.
- Do not animate every card into view; no scroll-triggered reveal sequence on a performance dashboard.

---

## 18. Accessibility and resilience

- WCAG AA contrast for meaningful text and controls. Small muted labels must not fade into low-contrast decoration.
- Keyboard access for navigation, graph selection, table actions, command palette, and dismissible overlays.
- Focus states are always visible and must not be conveyed only by colour.
- All charts need a textual summary and an accessible data table/value representation.
- SVG graph nodes have accessible labels; selecting a node must be possible without pointer dragging alone.
- `MEASURED`, `PROJECTED`, and `HYPOTHESIS` must always be available as text, even when colour is removed.
- On `prefers-reduced-motion`, stop all non-essential animation.
- With font loading disabled, layout remains coherent.
- With blur unsupported, glass surfaces become solid surfaces with unchanged contrast.
- High zoom / narrow viewport must preserve route names, units, run outcome, and critical warnings.
- Respect `NO_COLOR` for terminal output and use plain-text states in CI logs.

---

## 19. Responsive design

### Wide desktop (≥ 1280 px)

- Full sidebar, two aligned pressure charts, graph + inspector side-by-side.
- Table shows all key columns.
- One main page headline; only selected metadata is surfaced above the fold.

### Compact desktop / tablet (768–1279 px)

- Sidebar may collapse to icons + accessible labels on focus/hover.
- Graph inspector becomes a narrow side panel or a lower drawer.
- Metric strip wraps to two rows.
- Tables prioritize route, p95, errors, SLO, and source map state.

### Mobile (< 768 px)

- Compact top bar with repository and run state; navigation as a simple menu.
- Headline reduces to 30–34 px.
- Metric cells stack or use two columns.
- Charts stack naturally; maintain axis labels and threshold.
- Graph canvas has a fixed usable height, pan/zoom controls, and a compact bottom inspector.
- Keep source paths copyable; code paths must not be hidden behind hover-only affordances.

The mobile experience is a diagnostic summary and graph navigator, not a miniature desktop grid.

---

## 20. Dashboard data contract

The design assumes UI components consume actual structured run data. The backend's schema may differ; map it once into a presentation layer rather than duplicating interpretation throughout components.

Every rendered datum should retain:

```ts
type EvidenceClass = 'measured' | 'projected' | 'hypothesis';

type EvidenceRef = {
  id: string;
  kind: string;
  source: string;
  timestamp?: string;
  class: EvidenceClass;
};

type DisplayMetric = {
  value: number | string | null;
  unit?: string;
  label: string;
  class: EvidenceClass;
  evidence: EvidenceRef[];
  unavailableReason?: string;
};

type GraphRelation = {
  id: string;
  from: string;
  to: string;
  kind: string;
  provenance: 'entire_graph' | 'runtime_evidence' | 'hypothesis';
  sourceLocation?: string;
  runtimeTiming: 'measured' | 'not_measured';
};
```

These types express the interface contract, not the mandated backend schema. The production view must preserve the actual provider's provenance and metadata. Never default an absent number to zero or an absent confidence to `100%`.

### Empty and error states

A request failure must show the failed panel and a specific reason. Do not silently switch to fixture data. Demo fixtures are a separate, explicit mode and must have a persistent `DEMO DATA` label. If the graph provider is unavailable, show “Code map unavailable” plus the provider error; do not synthesize a graph from regex guesses unless that is an explicit, separately labelled source.

---

## 21. Single source of truth for tokens and copy

Recommended structure when implementation starts:

```text
design/
  DESIGN-SYSTEM.md          # this document
  tokens.css                # CSS custom properties
  tokens.json               # optional shared semantic values if CLI/web need them
  graph-semantics.md        # only if the graph contract becomes large enough
```

Avoid separate, nearly identical palettes in the React dashboard, report renderer, and CLI. The web CSS owns screen material and layout, but state names, semantic labels, evidence classes, and formatting functions should be shared or tested for parity.

Do not create a design-token framework, Storybook, theme editor, or extra package during the two-day MVP unless specifically approved. A small, direct token file is enough.

---

## 22. Implementation priorities

### P0 — identity and legibility

1. Lock type stacks and colour tokens.
2. Build the wordmark and small signal SVG.
3. Set page frame, header, navigation, spacing, buttons, labels, and the main metric strip.
4. Ensure all sample/demo values are visibly labelled as illustrative.

### P1 — the Loadline signature

5. Implement aligned load/latency charts with a real threshold line and breach marker.
6. Build the focused graph canvas and code inspector using actual Entire Graph output.
7. Connect selected operation → graph context → evidence ledger.
8. Keep static edges, measured pressure, and hypotheses visually distinct.

### P2 — trustworthy investigation

9. Render prediction/experiment/scoring events with stable IDs.
10. Build operation table sorting/filtering and command palette actions.
11. Add `report.md` and `report.json` file actions where those files actually exist.
12. Implement blocked/incomplete/no-bottleneck states as fully designed outcomes.

### P3 — finish polish

13. Keyboard interactions, responsive layouts, reduced motion, and contrast checks.
14. Verify graph/metric provenance labels and source path selection/copying.
15. Visual regression screenshots for one supported case, one blocker, and one incomplete run.

**MVP constraint:** the polished design must not become a reason to delay the core pipeline. If the dashboard is accepted into scope, deliver one run view with the strongest path: run summary → operation → code map → experiment → finding. Defer deep settings, arbitrary graph exploration, and ornamental animation.

---

## 23. Acceptance checklist

### Visual
- [ ] One editorial serif headline per major page, not one per section.
- [ ] UI typography is consistent and comfortably readable.
- [ ] Glass appears only on floating/context layers.
- [ ] Backgrounds stay warm and quiet; graph owns the dark stage.
- [ ] No gradients used as status or measurement semantics.
- [ ] Pressure red only appears for observed breach/failure.
- [ ] Hypotheses have a distinct visual grammar from measured data.
- [ ] All critical actions have obvious labels.

### Evidence
- [ ] Every displayed number resolves to a run event, metric, or declared derivation.
- [ ] Each graph relation reports its provenance; unknown edges are not invented.
- [ ] Runtime measurement never silently spreads through static graph adjacency.
- [ ] `MEASURED`, `PROJECTED`, and `HYPOTHESIS` remain distinct in colour-free text.
- [ ] A blocker or incomplete run looks intentional, but never successful.
- [ ] Demo values always carry a persistent illustrative-data label.

### Interaction
- [ ] Navigation, node selection, table selection, palette, copy action, and report links work.
- [ ] Keyboard navigation has visible focus.
- [ ] Reduced-motion and no-blur modes are readable.
- [ ] Mobile preserves units, labels, findings, and source links.

### Product scope
- [ ] Dashboard scope has been approved in `tech_doc.md` before implementation.
- [ ] The view is one run, not an unplanned observability platform.
- [ ] No forbidden features from the MVP's “Not in this build” list slip in under design polish.

---

## 24. Research links

- [Claude / Anthropic](https://claude.com/) — editorial warmth and clear long-form hierarchy.
- [Claude design-system setup](https://support.claude.com/en/articles/14604397-set-up-your-design-system-in-claude-design) — consistency across colours, typography, components, and layouts.
- [OpenAI brand guidelines](https://openai.com/brand/) — brand typography and identity usage.
- [OpenAI UI guidelines](https://developers.openai.com/plugins/concepts/ui-guidelines) — minimal UI, limited accent use, system-first typography.
- [Cursor](https://cursor.com/) — restrained product identity and developer-workbench feel.
- [Cursor design-system guidance](https://prod.cursor.com/for/designers) — reusable token and component rules.
- [Entire Graph](https://github.com/entireio/entire-graph) — actual code relationships, source locations, exports, coverage, and heuristic limitations.
- [k6 metrics](https://grafana.com/docs/k6/latest/using-k6/metrics/) — metrics and metric types.
- [k6 thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/) — explicit threshold evaluation.
- [k6 result output](https://grafana.com/docs/k6/latest/get-started/results-output/) — summary statistics and timestamped time series.
- [Linear](https://linear.app/) and [Sentry](https://sentry.io/) — references for restrained task UI and symptom-to-source investigation patterns.

---

## Final design rule

**Loadline should look calm enough that the evidence feels louder.**

One good headline. Four useful numbers. One real pressure timeline. One real code graph. One evidence-backed finding. Glass just around the edges. Everything else earns its place.
