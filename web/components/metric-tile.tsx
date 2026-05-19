type Props = {
  label: string;
  value: string;
  tone?: "neutral" | "warn" | "ok";
};

export function MetricTile({ label, value, tone = "neutral" }: Props) {
  const accent =
    tone === "warn"
      ? "text-signal-400"
      : tone === "ok"
      ? "text-ok-500"
      : "text-ink-100";

  return (
    <div className="rounded-md border border-ink-800 bg-ink-900/60 px-4 py-3">
      <div className="font-mono text-[11px] uppercase tracking-wider text-ink-500">
        {label}
      </div>
      <div className={`mt-1 text-lg font-medium ${accent}`}>{value}</div>
    </div>
  );
}
