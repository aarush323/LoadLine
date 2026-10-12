import { REPO_URL } from "./repo";
import { LoadlineMark } from "./LoadlineMark";

export function LandingNav() {
  return (
    <div className="landing-nav-wrap">
      <div className="content landing-nav">
        <a href="#hero" className="no-underline">
          <LoadlineMark size="sm" />
        </a>
        <nav className="landing-nav-links" aria-label="Page">
          <a href="#how">How it works</a>
          <a href="#outcome">Why Loadline</a>
          <a href="#quickstart">Quickstart</a>
          <a href={REPO_URL} target="_blank" rel="noreferrer">GitHub</a>
        </nav>
        <a href="#quickstart" className="btn-ascii btn-ascii-fill landing-nav-cta">Get started</a>
      </div>
    </div>
  );
}
