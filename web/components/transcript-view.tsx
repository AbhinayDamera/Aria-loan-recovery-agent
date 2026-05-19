"use client";

import { useEffect, useRef } from "react";
import type { TranscriptTurn } from "@/lib/types";

const INTENT_STYLES: Record<string, { bg: string; fg: string; label: string }> = {
  hardship: { bg: "bg-signal-100", fg: "text-signal-900", label: "hardship signal" },
  distress: { bg: "bg-signal-400", fg: "text-signal-900", label: "distress" },
  promise_to_pay: { bg: "bg-ok-500/30", fg: "text-ok-500", label: "PTP captured" },
  dispute: { bg: "bg-amber-200", fg: "text-amber-900", label: "dispute" },
  affordability: { bg: "bg-ink-300", fg: "text-ink-900", label: "partial pay" },
  cooperative: { bg: "bg-ok-500/20", fg: "text-ok-500", label: "cooperative" },
  avoidance: { bg: "bg-ink-700", fg: "text-ink-200", label: "avoidance" },
};

export function TranscriptView({ turns }: { turns: TranscriptTurn[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, [turns.length]);

  return (
    <div
      ref={ref}
      className="thin-scroll max-h-72 overflow-y-auto pr-2 text-sm leading-relaxed"
    >
      {turns.length === 0 && (
        <p className="text-ink-500 italic">Waiting for the call to begin…</p>
      )}

      {turns.map((turn, i) => {
        const isBorrower = turn.role === "borrower";
        const tag = turn.intent ? INTENT_STYLES[turn.intent] : null;

        return (
          <div key={i} className="mb-3">
            <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-ink-500">
              <span>{isBorrower ? "Borrower" : "Aria"}</span>
              <span>·</span>
              <span>{formatTime(turn.ts)}</span>
              {tag && (
                <span className={`ml-1 rounded px-1.5 py-0.5 text-[10px] ${tag.bg} ${tag.fg}`}>
                  {tag.label}
                </span>
              )}
            </div>
            <p
              className={
                isBorrower
                  ? "mt-1 text-ink-100"
                  : "mt-1 text-ink-300"
              }
            >
              {turn.text}
            </p>
          </div>
        );
      })}
    </div>
  );
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { minute: "2-digit", second: "2-digit" });
}
