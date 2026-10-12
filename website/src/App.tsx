import HeroAsciiOne from "@/components/ui/hero-ascii-one";
import { Close } from "./components/Close";
import { LandingNav } from "./components/LandingNav";
import { Quickstart } from "./components/Quickstart";
import { SafetyBand } from "./components/SafetyBand";

export default function App() {
  return (
    <>
      <HeroAsciiOne />
      <div id="page">
        <LandingNav />
        <main>
          <section className="proof-strip">
            <div className="content">
              <span className="section-kicker">Loadline</span>
              <p className="proof-intro">
                When latency spikes in staging, someone still has to open the right files. Loadline connects load
                tests to your repository and leaves a report your team can ship—or a blocker you can trust.
              </p>
              <div className="proof-grid">
                <div>
                  <h3>Your app, under pressure</h3>
                  <p>Real HTTP traffic against the service you boot locally—not a disconnected micro-benchmark.</p>
                </div>
                <div>
                  <h3>Code in the conversation</h3>
                  <p>Search and read the repo alongside k6 runs so findings point somewhere specific.</p>
                </div>
                <div>
                  <h3>Output you can forward</h3>
                  <p>A Markdown investigation with verdict, context, and limits—ready for review.</p>
                </div>
              </div>
            </div>
          </section>

          <section id="how" className="section">
            <div className="content">
              <span className="section-kicker">Process</span>
              <h2>Four steps from repo to report</h2>
              <ol className="steps">
                <li>
                  <span>01</span>
                  <div>
                    <strong>Point at a repo</strong>
                    <p>Supported HTTP apps with Docker or Compose. If it doesn’t fit, you get a clear no—not silence.</p>
                  </div>
                </li>
                <li>
                  <span>02</span>
                  <div>
                    <strong>Boot and load</strong>
                    <p>Controlled k6 traffic while the stack runs in a constrained environment on your machine.</p>
                  </div>
                </li>
                <li>
                  <span>03</span>
                  <div>
                    <strong>Investigate</strong>
                    <p>One agent searches the codebase, reads files, and runs focused load experiments.</p>
                  </div>
                </li>
                <li>
                  <span>04</span>
                  <div>
                    <strong>Deliver</strong>
                    <p>Written findings on disk—or an honest stop when the target won’t boot.</p>
                  </div>
                </li>
              </ol>
            </div>
          </section>

          <section id="outcome" className="section">
            <div className="content split">
              <div>
                <span className="section-kicker">Why Loadline</span>
                <h2>After the chart bends, you need a next step.</h2>
                <p className="lead">
                  Loadline is for teams who have seen the curve move and need to know what to read in the codebase—not
                  another dashboard tile or chat thread.
                </p>
                <ul className="bullets">
                  <li>Runs on your laptop from source—no mystery SaaS.</li>
                  <li>Fits how you already work: Docker, k6, your model provider.</li>
                  <li>Optional tracing when you want it; not required to start.</li>
                </ul>
              </div>
              <div className="report-card">
                <p className="report-label">Example report shape</p>
                <pre className="report-snippet">{`Verdict
  What degraded, and under what load

Context
  Routes and files worth reading next

Next
  A narrower experiment—or stop with a blocker

Limits
  Sandbox run, not production proof`}</pre>
              </div>
            </div>
          </section>

          <SafetyBand />
          <Quickstart />
        </main>
        <Close />
      </div>
    </>
  );
}
