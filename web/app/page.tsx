"use client";

import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import { LiveCallCard } from "@/components/live-call-card";
import { BorrowerQueue } from "@/components/borrower-queue";
import { BorrowerProfile } from "@/components/borrower-profile";
import { StatsHeader } from "@/components/stats-header";
import { useAriaSocket } from "@/lib/socket";
import { getStats } from "@/lib/api";
import type {
  AriaEvent,
  EmotionPoint,
  Stats,
  TranscriptTurn,
} from "@/lib/types";

type ThinkingStep = {
  label: string;
  detail: string;
  ts: number;
};

type CallState = {
  callId: string | null;
  borrowerId: string | null;
  borrowerName: string;
  overdueAmount: number;
  daysOverdue: number;
  startedAt: number | null;
  sentiment: string;
  intent: string;
  ptpStatus: string;
  emotionPoints: EmotionPoint[];
  turns: TranscriptTurn[];
  escalated: boolean;
  durationSeconds: number;
  personalityMode: string;
  personalityReason: string;
  thinkingSteps: ThinkingStep[];
  currentThinking: string;
};

const initialCallState: CallState = {
  callId: null,
  borrowerId: null,
  borrowerName: "—",
  overdueAmount: 0,
  daysOverdue: 0,
  startedAt: null,
  sentiment: "—",
  intent: "—",
  ptpStatus: "Pending",
  emotionPoints: [],
  turns: [],
  escalated: false,
  durationSeconds: 0,
  personalityMode: "—",
  personalityReason: "",
  thinkingSteps: [],
  currentThinking: "",
};

function callReducer(state: CallState, e: AriaEvent): CallState {
  const t = state.startedAt ? Math.max(0, e.timestamp - state.startedAt) : 0;

  switch (e.type) {
    case "call_started": {
      const borrowerId = (e.payload.borrower_id as string) ?? null;
      return {
        ...initialCallState,
        callId: e.call_id,
        borrowerId,
        startedAt: e.timestamp,
        borrowerName: (e.payload.borrower_name as string) ?? "—",
        overdueAmount: (e.payload.overdue_amount as number) ?? 0,
        daysOverdue: (e.payload.days_overdue as number) ?? 0,
      };
    }

    case "transcript": {
      const turn: TranscriptTurn = {
        role: (e.payload.role as TranscriptTurn["role"]) ?? "borrower",
        text: (e.payload.text as string) ?? "",
        intent: e.payload.intent as TranscriptTurn["intent"],
        ts: e.timestamp,
      };
      return {
        ...state,
        turns: [...state.turns, turn],
        durationSeconds: t,
        currentThinking: turn.role === "aria" ? "" : state.currentThinking,
      };
    }

    case "intent": {
      const payload = e.payload;

      if (payload.thinking_label) {
        const step: ThinkingStep = {
          label: payload.thinking_label as string,
          detail: (payload.thinking_detail as string) ?? "",
          ts: e.timestamp,
        };
        return {
          ...state,
          thinkingSteps: [...state.thinkingSteps, step].slice(-10),
          currentThinking: `${step.label}: ${step.detail}`,
        };
      }

      if (payload.personality_mode) {
        return {
          ...state,
          personalityMode: payload.personality_mode as string,
          personalityReason: (payload.personality_reason as string) ?? "",
        };
      }

      if (payload.intent) {
        const intent = payload.intent as string;
        return {
          ...state,
          intent: prettyIntent(intent),
          sentiment:
            intent === "distress" || intent === "hardship"
              ? "Anxious"
              : intent === "cooperative"
                ? "Engaged"
                : state.sentiment,
          turns: tagLastBorrowerTurn(state.turns, intent),
        };
      }

      return state;
    }

    case "emotion": {
      const score = (e.payload.score as number) ?? 0;
      const next = [...state.emotionPoints, { t, score }];
      return { ...state, emotionPoints: next.slice(-120) };
    }

    case "ptp_captured":
      return { ...state, ptpStatus: "Captured" };

    case "escalation":
      return { ...state, escalated: true };

    case "call_ended":
      return { ...state, durationSeconds: t, currentThinking: "" };

    default:
      return state;
  }
}

function prettyIntent(intent: string): string {
  return {
    promise_to_pay: "Promise",
    hardship: "Hardship",
    distress: "Distress",
    dispute: "Dispute",
    avoidance: "Avoidance",
    cooperative: "Cooperative",
    affordability: "Partial",
  }[intent] ?? "—";
}

function tagLastBorrowerTurn(
  turns: TranscriptTurn[],
  intent: string,
): TranscriptTurn[] {
  if (intent === "none") return turns;
  for (let i = turns.length - 1; i >= 0; i--) {
    if (turns[i].role === "borrower" && !turns[i].intent) {
      const copy = [...turns];
      copy[i] = { ...copy[i], intent: intent as TranscriptTurn["intent"] };
      return copy;
    }
  }
  return turns;
}


export default function DashboardPage() {
  const [callState, dispatch] = useReducer(callReducer, initialCallState);
  const [selectedBorrowerId, setSelectedBorrowerId] = useState<string | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [statsKey, setStatsKey] = useState(0);

  const handle = useCallback((e: AriaEvent) => dispatch(e), []);
  const { connected } = useAriaSocket(callState.callId, handle);

  // Refresh stats periodically
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      getStats()
        .then((s) => {
          if (!cancelled) setStats(s);
        })
        .catch(() => {});
    };
    load();
    const t = setInterval(load, 10000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [statsKey]);

  // When a call ends, refresh stats
  useEffect(() => {
    if (callState.startedAt && callState.durationSeconds > 0 && !callState.callId) {
      setStatsKey((k) => k + 1);
    }
  }, [callState.callId, callState.durationSeconds, callState.startedAt]);

  const isLive = useMemo(
    () => callState.callId !== null && callState.startedAt !== null,
    [callState.callId, callState.startedAt],
  );

  // When call starts, auto-select the borrower
  useEffect(() => {
    if (callState.borrowerId) {
      setSelectedBorrowerId(callState.borrowerId);
    }
  }, [callState.borrowerId]);

  return (
    <main className="mx-auto max-w-[1400px] px-4 py-6">
      {/* Header */}
      <header className="mb-6 flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-medium tracking-tight">Aria</h1>
          <p className="font-mono text-[11px] uppercase tracking-wider text-ink-500">
            Recovery operations console
          </p>
        </div>
        <div className="flex items-center gap-4">
          <span className="font-mono text-[10px] uppercase tracking-wider text-ink-500">
            ✓ RBI Fair Practices · DPDP compliant
          </span>
          <span className="font-mono text-[11px] uppercase tracking-wider">
            {connected ? (
              <span className="text-ok-500">● connected</span>
            ) : (
              <span className="text-signal-400">● reconnecting</span>
            )}
          </span>
        </div>
      </header>

      {/* Stats */}
      <div className="mb-6">
        <StatsHeader stats={stats} loading={stats === null} />
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[360px_1fr]">
        {/* Sidebar */}
        <div className="lg:h-[calc(100vh-220px)] lg:min-h-[600px]">
          <BorrowerQueue
            selectedId={selectedBorrowerId}
            activeCallBorrowerId={isLive ? callState.borrowerId : null}
            onSelect={setSelectedBorrowerId}
          />
        </div>

        {/* Main panel */}
        <div className="space-y-4 lg:overflow-auto lg:h-[calc(100vh-220px)] lg:min-h-[600px]">
          {isLive ? (
            <LiveView callState={callState} />
          ) : selectedBorrowerId ? (
            <BorrowerProfile
              borrowerId={selectedBorrowerId}
              onCallTriggered={() => setStatsKey((k) => k + 1)}
            />
          ) : (
            <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-ink-700 px-8 py-16 text-center text-ink-500">
              <div>
                <p className="mb-2 text-sm">Select a borrower from the queue.</p>
                <p className="font-mono text-[11px]">
                  Aria will show their profile, payment history, and past calls here.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}


function LiveView({ callState }: { callState: CallState }) {
  return (
    <div className="space-y-4">
      {/* Thinking indicator */}
      {callState.currentThinking && (
        <div className="rounded-lg border border-ok-500/40 bg-ok-900/10 px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-ok-500" />
            <span className="font-mono text-[10px] uppercase tracking-wider text-ok-500">
              Aria is thinking
            </span>
            <span className="text-sm text-ink-200">{callState.currentThinking}</span>
          </div>
        </div>
      )}

      {/* Personality mode */}
      {callState.personalityMode !== "—" && (
        <div className="flex items-center gap-3 font-mono text-xs">
          <span className="uppercase tracking-wider text-ink-500">Mode</span>
          <span
            className={`rounded px-2 py-0.5 uppercase ${
              callState.personalityMode === "gentle"
                ? "bg-blue-900/50 text-blue-200"
                : callState.personalityMode === "firm"
                  ? "bg-amber-900/50 text-amber-200"
                  : "bg-emerald-900/50 text-emerald-200"
            }`}
          >
            {callState.personalityMode}
          </span>
          {callState.personalityReason && (
            <span className="text-ink-500">— {callState.personalityReason}</span>
          )}
        </div>
      )}

      <LiveCallCard
        callId={callState.callId!}
        borrowerName={callState.borrowerName}
        overdueAmount={callState.overdueAmount}
        daysOverdue={callState.daysOverdue}
        durationSeconds={callState.durationSeconds}
        sentiment={callState.sentiment}
        intent={callState.intent}
        ptpStatus={callState.ptpStatus}
        emotionPoints={callState.emotionPoints}
        turns={callState.turns}
        escalated={callState.escalated}
      />

      {/* Reasoning timeline */}
      {callState.thinkingSteps.length > 0 && (
        <div className="rounded-lg border border-ink-700 px-4 py-4">
          <h3 className="mb-3 font-mono text-[10px] uppercase tracking-wider text-ink-500">
            Reasoning timeline
          </h3>
          <ol className="space-y-2">
            {callState.thinkingSteps.slice(-6).map((step, i) => (
              <li key={i} className="flex gap-3 text-sm">
                <span className="font-mono text-[10px] uppercase text-ink-400 w-24 flex-shrink-0">
                  {step.label}
                </span>
                <span className="text-ink-200">{step.detail}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
