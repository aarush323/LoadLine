import { CopyCodeButton } from "./CopyCodeButton";

const COMMANDS = `uv sync
cp .env.example .env
uv run loadline doctor
uv run loadline run --repo /absolute/path/to/your-app`;

export function Quickstart() {
  return (
    <section id="quickstart" className="section">
      <div className="content narrow">
        <span className="section-kicker">Get started</span>
        <h2>Run Loadline on your machine</h2>
        <p className="lead">
          Clone NeatHacks, install with <code>uv</code>, add your model key, and point at an app you can boot locally.
        </p>
        <CopyCodeButton code={COMMANDS} label="Copy commands" />
        <pre className="code-block">{COMMANDS}</pre>
        <p className="fine">
          Python 3.12 · Docker with Compose v2 · Git 2.36+. Install from source today—no PyPI package yet.
        </p>
      </div>
    </section>
  );
}
