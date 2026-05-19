"use client";

import { MetricTile } from "./metric-tile";
import { TranscriptView } from "./transcript-view";
import { EmotionChart } from "./emotion-chart";
import type { EmotionPoint, TranscriptTurn } from "@/lib/types";

type Props = {
  callId: string;
  borrowerName: string;
  overdueAmount: number;
  daysOverdue: number;
  durationSeconds: number;
  sentiment: string;
  intent: string;
  ptpStatus: string;
  emotionPoints: EmotionPoint[];
  turns: TranscriptTurn[];
  escalated: boolean;
};

export function LiveCallCard(props: Props) {
  return (
    <article className="rounded-lg border border-ink-800 bg-ink-900/40 p-5">
      {/* header */}
      <header className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span
            className={`h-2 w-2 rounded-full ${
              props.escalated ? "bg-signal-500" : "bg-signal-600"
            } animate-pulse-dot`}
          />
          <div>
            <p className="font-medium">
              Live call · <span className="text-ink-100">{props.borrowerName}</span>
            </p>
            <p className="font-mono text-xs text-ink-500">
              EMI overdue · {props.daysOverdue} days · ₹
              {props.overdueAmount.toLocaleString("en-IN")}
            </p>
          </div>
        </div>
        <div className="font-mono text-xs tabular-nums text-ink-400">
          {formatDuration(props.durationSeconds)}
        </div>
      </header>

      {/* metric strip */}
      <div className="mb-4 grid grid-cols-3 gap-2">
        <MetricTile
          label="Sentiment"
          value={props.sentiment}
          tone={props.sentiment.toLowerCase() === "anxious" ? "warn" : "neutral"}
        />
        <MetricTile
          label="Intent"
          value={props.intent}
          tone={props.intent.toLowerCase() === "hardship" ? "warn" : "neutral"}
        />
        <MetricTile
          label="PTP"
          value={props.ptpStatus}
          tone={props.ptpStatus === "Captured" ? "ok" : "neutral"}
        />
      </div>

      {/* emotion graph */}
      <div className="mb-4">
        <p className="mb-1 font-mono text-[11px] uppercase tracking-wider text-ink-500">
          Emotional stress · live
        </p>
        <EmotionChart data={props.emotionPoints} />
      </div>

      {/* transcript */}
      <div className="border-t border-ink-800 pt-3">
        <p className="mb-2 font-mono text-[11px] uppercase tracking-wider text-ink-500">
          Live transcript
        </p>
        <TranscriptView turns={props.turns} />
      </div>

      {props.escalated && (
        <div className="mt-4 rounded-md border border-signal-700 bg-signal-900/30 px-3 py-2 text-sm text-signal-100">
          Distress threshold crossed · routing to a human operator
        </div>
      )}
    </article>
  );
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60).toString();
  const s = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}
