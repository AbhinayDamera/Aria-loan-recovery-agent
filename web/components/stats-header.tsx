"use client";

import type { Stats } from "@/lib/types";

type Props = {
  stats: Stats | null;
  loading?: boolean;
};

export function StatsHeader({ stats, loading }: Props) {
  if (loading || !stats) {
    return (
      <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="h-16 rounded-lg border border-ink-700 bg-ink-900/30 animate-pulse"
          />
        ))}
      </div>
    );
  }

  const cells: { label: string; value: string; tone?: string }[] = [
    {
      label: "Calls today",
      value: String(stats.calls_today),
    },
    {
      label: "PTPs today",
      value: String(stats.ptps_today),
      tone: "text-ok-500",
    },
    {
      label: "PTP rate (30d)",
      value: `${stats.ptp_rate_30d}%`,
    },
    {
      label: "Queue",
      value: String(stats.queue_total),
    },
    {
      label: "Critical",
      value: String(stats.queue_critical),
      tone: "text-signal-400",
    },
    {
      label: "Total overdue",
      value: `₹${formatINR(stats.total_overdue_amount)}`,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
      {cells.map((c) => (
        <div
          key={c.label}
          className="rounded-lg border border-ink-700 px-4 py-3"
        >
          <div className="font-mono text-[10px] uppercase tracking-wider text-ink-500">
            {c.label}
          </div>
          <div className={`mt-1 text-xl font-semibold ${c.tone ?? "text-ink-100"}`}>
            {c.value}
          </div>
        </div>
      ))}
    </div>
  );
}

function formatINR(n: number): string {
  if (n >= 10_00_000) return `${(n / 10_00_000).toFixed(1)}L`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}
