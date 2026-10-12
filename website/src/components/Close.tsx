import { LoadlineMark } from "./LoadlineMark";
import { REPO_URL } from "./repo";

export function Close() {
  return (
    <footer className="footer">
      <div className="content footer-row">
        <div>
          <LoadlineMark size="md" />
          <h2 style={{ marginTop: "1.25rem" }}>Know where your system bends.</h2>
          <a href="#quickstart" className="btn-ascii btn-ascii-fill" style={{ marginTop: "0.5rem" }}>
            Run Loadline
          </a>
        </div>
        <div className="footer-meta">
          <a href={REPO_URL}>NeatHacks on GitHub</a>
          <p className="fine">Loadline 0.1.0 · open-source CLI</p>
        </div>
      </div>
    </footer>
  );
}
