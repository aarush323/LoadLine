import { useState } from "react";

type Props = { code: string; label?: string };

export function CopyCodeButton({ code, label = "Copy commands" }: Props) {
  const [state, setState] = useState<"idle" | "ok" | "fail">("idle");

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setState("ok");
      setTimeout(() => setState("idle"), 2000);
    } catch {
      setState("fail");
      setTimeout(() => setState("idle"), 2500);
    }
  }

  const msg = state === "ok" ? "Copied to clipboard" : state === "fail" ? "Copy failed" : "";

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        onClick={copy}
        className="btn-ascii btn-ascii-fill"
      >
        {label}
      </button>
      <span className="text-sm text-[var(--muted)]" role="status" aria-live="polite">
        {msg}
      </span>
    </div>
  );
}
