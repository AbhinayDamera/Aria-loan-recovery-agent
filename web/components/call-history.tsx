"use client";

import type { PastCall } from "@/lib/types";

type Props = {
  calls: PastCall[];
};

export function CallHistory({ calls }: Props) {
  if (calls.length === 0) {
    return (
      <div className="text-xs text-ink-500">
        No previous calls. The next call will be the first contact.
      </div>
    );
  }

  return (
    <ol className="space-y-3">
      {calls.map((c) => (
        <CallCard key={c.id} call={c} />
      ))}
    </ol>
  );
}

function CallCard({ call }: { call: PastCall }) {
  const date = new Date(call.started_at);
  const dateStr = date.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
  });
  const timeStr = date.toLocaleTimeString("en-IN", {
    hour: "numeric",
    minute: "2-digit",
  });

  const duration = call.duration_seconds
    ? `${Math.floor(call.duration_seconds / 60)}m ${call.duration_seconds % 60}s`
    : "—";

  return (
    <li className="rounded-md border border-ink-800 bg-ink-900/40 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-sm">
            <span className="font-medium text-ink-100">{dateStr}</span>
            <span className="text-ink-500">at {timeStr}</span>
            <span className="text-ink-500">·</span>
            <span className="font-mono text-xs text-ink-400">{duration}</span>
            {call.escalated && (
              <span className="rounded bg-red-900/50 px-1.5 py-0.5 font-mono text-[9px] uppercase text-red-300">
                escalated
              </span>
            )}
          </div>
          {call.summary && (
            <p className="mt-1.5 text-sm text-ink-200 leading-relaxed">
              {call.summary}
            </p>
          )}
          {call.promises_made && call.promises_made.length > 0 && (
            <div className="mt-2">
              <div className="font-mono text-[9px] uppercase tracking-wider text-ok-500">
                Promises
              </div>
              <ul className="mt-0.5 text-xs text-ink-300">
                {call.promises_made.map((p, i) => (
                  <li key={i}>• {p}</li>
                ))}
              </ul>
            </div>
          )}
          {call.concerns_raised && call.concerns_raised.length > 0 && (
            <div className="mt-2">
              <div className="font-mono text-[9px] uppercase tracking-wider text-amber-500">
                Concerns
              </div>
              <ul className="mt-0.5 text-xs text-ink-400">
                {call.concerns_raised.map((c, i) => (
                  <li key={i}>• {c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <OutcomeTag outcome={call.outcome} />
      </div>
    </li>
  );
}

function OutcomeTag({ outcome }: { outcome: string | null }) {
  if (!outcome) return null;

  const label = {
    ptp_captured: "PTP",
    hardship_logged: "Hardship",
    dispute: "Dispute",
    no_answer: "No answer",
    escalated: "Escalated",
    dnc_requested: "DNC",
  }[outcome] ?? outcome;

  const tone = {
    ptp_captured: "bg-emerald-900/50 text-emerald-300",
    hardship_logged: "bg-amber-900/50 text-amber-300",
    dispute: "bg-purple-900/50 text-purple-300",
    no_answer: "bg-ink-800 text-ink-400",
    escalated: "bg-red-900/50 text-red-300",
    dnc_requested: "bg-red-900/50 text-red-300",
  }[outcome] ?? "bg-ink-800 text-ink-400";

  return (
    <span
      className={`shrink-0 rounded px-2 py-0.5 font-mono text-[10px] uppercase ${tone}`}
    >
      {label}
    </span>
  );
}
