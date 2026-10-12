import { useEffect } from "react";
import { REPO_URL } from "@/components/repo";
import { LoadlineMark } from "@/components/LoadlineMark";
import "@/styles/hero-ascii.css";

const UNICORN_PROJECT = "OMzqyUv6M3kSnv0JeAtC";

export default function HeroAsciiOne() {
  useEffect(() => {
    const embedScript = document.createElement("script");
    embedScript.type = "text/javascript";
    embedScript.textContent = `
      !function(){
        if(!window.UnicornStudio){
          window.UnicornStudio={isInitialized:!1};
          var i=document.createElement("script");
          i.src="https://cdn.jsdelivr.net/gh/hiunicornstudio/unicornstudio.js@v1.4.33/dist/unicornStudio.umd.js";
          i.onload=function(){
            window.UnicornStudio.isInitialized||(UnicornStudio.init(),window.UnicornStudio.isInitialized=!0)
          };
          (document.head || document.body).appendChild(i)
        }
      }();
    `;
    document.head.appendChild(embedScript);

    const style = document.createElement("style");
    style.textContent = `
      [data-us-project] a[href*="unicorn"],
      [data-us-project] [class*="watermark"] { display: none !important; }
    `;
    document.head.appendChild(style);

    const hideBranding = () => {
      document.querySelectorAll("[data-us-project] *").forEach((el) => {
        const text = (el.textContent || "").toLowerCase();
        if (text.includes("made with") || text.includes("unicorn")) {
          (el as HTMLElement).style.display = "none";
        }
      });
    };
    hideBranding();
    const interval = window.setInterval(hideBranding, 300);

    return () => {
      window.clearInterval(interval);
      embedScript.remove();
      style.remove();
    };
  }, []);

  return (
    <section id="hero" className="hero-ascii relative min-h-screen overflow-hidden bg-black">
      <div className="absolute inset-0 hidden h-full w-full lg:block">
        <div data-us-project={UNICORN_PROJECT} className="h-full min-h-screen w-full" />
      </div>
      <div className="hero-ascii-scrim" aria-hidden="true" />
      <div className="absolute inset-0 h-full w-full ascii-stars lg:hidden" aria-hidden="true" />

      <header className="absolute top-0 right-0 left-0 z-20 border-b border-white/15">
        <div className="content flex items-center justify-between py-4 lg:py-5">
          <a href="#hero" className="no-underline">
            <LoadlineMark size="md" />
          </a>
          <nav className="hidden items-center gap-8 font-mono text-[11px] tracking-wide text-white/55 uppercase md:flex">
            <a href="#how" className="hover:text-white">How it works</a>
            <a href="#quickstart" className="hover:text-white">Quickstart</a>
            <a href={REPO_URL} target="_blank" rel="noreferrer" className="hover:text-white">GitHub</a>
          </nav>
          <a href="#quickstart" className="btn-ascii btn-ascii-fill hidden text-[11px] md:inline-flex">Get started</a>
        </div>
      </header>

      <div className="frame-corner frame-tl" />
      <div className="frame-corner frame-tr" />
      <div className="frame-corner frame-bl" />
      <div className="frame-corner frame-br" />

      <div className="relative z-10 flex min-h-screen items-center pt-24 pb-[12vh] lg:pt-20">
        <div className="content w-full">
          <div className="hero-product max-w-2xl">
            <LoadlineMark size="hero" />
            <p className="hero-product-tag">Capacity investigation for production-bound teams</p>
            <h1 className="hero-product-headline">
              Find the breaking point
              <em> before production does.</em>
            </h1>
            <p className="hero-product-lead">
              Loadline boots your HTTP app locally, runs controlled load with k6, and writes an investigation your
              engineers can act on—verdict, code context, and limits. Not another vague latency screenshot.
            </p>
            <div className="hero-product-cta">
              <a href="#quickstart" className="btn-ascii btn-ascii-fill group">
                <span className="corner corner-tl" />
                <span className="corner corner-br" />
                Run on your repo
              </a>
              <a href="#how" className="btn-ascii">See how it works</a>
            </div>
          </div>
        </div>
      </div>

      <div className="hero-ascii-footer">
        <div className="content flex justify-between font-mono text-[9px] tracking-wide text-white/45 uppercase">
          <span>Local CLI</span>
          <span className="hidden sm:inline">Repo in · load out · evidence back</span>
          <span>Open source</span>
        </div>
      </div>
    </section>
  );
}
