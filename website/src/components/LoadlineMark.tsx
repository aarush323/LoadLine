type Props = { size?: "sm" | "md" | "hero"; showWord?: boolean };

export function LoadlineMark({ size = "md", showWord = true }: Props) {
  const icon = size === "sm" ? 26 : size === "hero" ? 48 : 32;
  const word =
    size === "hero"
      ? "text-[clamp(2.75rem,8vw,5.5rem)]"
      : size === "md"
        ? "text-xl lg:text-2xl"
        : "text-base";
  return (
    <span className="inline-flex items-center gap-3">
      <svg width={icon} height={icon} viewBox="0 0 34 34" aria-hidden="true" className="shrink-0">
        <rect width="34" height="34" rx="8" fill="#0a0c0b" stroke="rgba(255,255,255,0.22)" />
        <path
          d="M5 24 L11 24 L15 11 L19 19 L23 15 L29 15"
          fill="none"
          stroke="#c7ff70"
          strokeWidth="2.2"
          strokeLinecap="round"
        />
      </svg>
      {showWord && (
        <span className={`font-mono font-bold tracking-[0.06em] text-white italic ${word}`}>Loadline</span>
      )}
    </span>
  );
}
