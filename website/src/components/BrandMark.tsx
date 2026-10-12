type Props = { variant?: "light" | "dark"; showWord?: boolean };

export function BrandMark({ variant = "dark", showWord = true }: Props) {
  const stroke = "var(--signal)";
  const text = variant === "light" ? "var(--hero-copy)" : "var(--ink)";
  return (
    <a href="#" className="inline-flex items-center gap-2.5 no-underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--signal)]" aria-label="Loadline home">
      <svg width="34" height="34" viewBox="0 0 34 34" aria-hidden="true">
        <rect width="34" height="34" rx="9" fill={variant === "light" ? "#0f1411" : "#080b09"} stroke="var(--hero-line)" />
        <path
          d="M5 24 L11 24 L15 11 L19 19 L23 15 L29 15"
          fill="none"
          stroke={stroke}
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <line x1="5" y1="26" x2="29" y2="26" stroke="rgba(242,240,232,0.15)" strokeWidth="1" />
      </svg>
      {showWord && (
        <span className="text-lg font-semibold tracking-tight" style={{ color: text }}>
          Loadline
        </span>
      )}
    </a>
  );
}
