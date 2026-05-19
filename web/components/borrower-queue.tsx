"use client";

import { useEffect, useState } from "react";
import type { Borrower, RiskTier } from "@/lib/types";
import { callBorrower, listBorrowers } from "@/lib/api";
import { QuickCallForm } from "./quick-call-form";

type Props = {
  selectedId: string | null;
  activeCallBorrowerId: string | null;
  onSelect: (id: string) => void;
};

const FILTERS = [
  { label: "All", value: "" },
  { label: "Hardship", value: "hardship" },
  { label: "Distress", value: "distress" },
  { label: "Avoidance", value: "avoidance" },
  { label: "PTP", value: "promise_to_pay" },
  { label: "Cooperative", value: "cooperative" },
];

const SORTS = [
  { label: "Most overdue", value: "days_overdue" },
  { label: "Highest amount", value: "overdue_amount" },
  { label: "Risk score", value: "risk_score" },
  { label: "Last contacted", value: "last_contacted" },
  { label: "Name", value: "name" },
];

export function BorrowerQueue({
  selectedId,
  activeCallBorrowerId,
  onSelect,
}: Props) {
  const [borrowers, setBorrowers] = useState<Borrower[]>([]);
  const [loading, setLoading] = useState(true);
  const [intentFilter, setIntentFilter] = useState("");
  const [sort, setSort] = useState("days_overdue");
  const [callingId, setCallingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    listBorrowers({
      intent: intentFilter || undefined,
      sort,
    })
      .then((r) => {
        setBorrowers(r.borrowers);
        setLoading(false);
      })
      .catch((e) => {
        setError(String(e));
        setLoading(false);
      });
  }, [intentFilter, sort]);

  const handleCall = async (id: string) => {
    if (callingId) return; // one at a time
    setCallingId(id);
    try {
      await callBorrower(id);
    } catch (e) {
      setError(`Call failed: ${e}`);
    } finally {
      setTimeout(() => setCallingId(null), 1500);
    }
  };

  return (
    <aside className="flex h-full flex-col rounded-lg border border-ink-700">
      {/* Filter bar */}
      <div className="border-b border-ink-700 p-3 space-y-2">
        <div className="flex flex-wrap gap-1.5">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setIntentFilter(f.value)}
              className={`rounded px-2 py-1 font-mono text-[10px] uppercase tracking-wider transition ${
                intentFilter === f.value
                  ? "bg-ink-100 text-ink-900"
                  : "bg-ink-900/50 text-ink-400 hover:text-ink-200"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="w-full rounded border border-ink-700 bg-ink-900/50 px-2 py-1.5 text-xs text-ink-200 focus:border-ink-500 focus:outline-none"
        >
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              Sort: {s.label}
            </option>
          ))}
        </select>
      </div>

      {/* List */}
      <div className="flex-1 overflow-auto p-2">
        {error && (
          <div className="px-3 py-2 text-xs text-signal-400">{error}</div>
        )}
        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="h-20 rounded border border-ink-800 bg-ink-900/30 animate-pulse"
              />
            ))}
          </div>
        ) : borrowers.length === 0 ? (
          <div className="px-3 py-8 text-center text-xs text-ink-500">
            No borrowers match this filter.
          </div>
        ) : (
          <ul className="space-y-1.5">
            {borrowers.map((b) => (
              <BorrowerRow
                key={b.id}
                b={b}
                selected={selectedId === b.id}
                isActiveCall={activeCallBorrowerId === b.id}
                calling={callingId === b.id}
                onSelect={() => onSelect(b.id)}
                onCall={() => handleCall(b.id)}
              />
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-ink-700 px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-500">
        {borrowers.length} borrower{borrowers.length !== 1 ? "s" : ""}
      </div>

      {/* Quick-call form for testing other phone numbers */}
      <QuickCallForm />
    </aside>
  );
}


function BorrowerRow({
  b,
  selected,
  isActiveCall,
  calling,
  onSelect,
  onCall,
}: {
  b: Borrower;
  selected: boolean;
  isActiveCall: boolean;
  calling: boolean;
  onSelect: () => void;
  onCall: () => void;
}) {
  return (
    <li
      onClick={onSelect}
      className={`group cursor-pointer rounded border px-3 py-2 transition ${
        selected
          ? "border-ink-400 bg-ink-900"
          : "border-ink-800 bg-ink-900/40 hover:border-ink-600"
      } ${isActiveCall ? "ring-1 ring-ok-500" : ""}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <RiskDot tier={b.risk_tier} />
            <span className="truncate text-sm font-medium text-ink-100">
              {b.name}
            </span>
            {isActiveCall && (
              <span className="text-[10px] uppercase text-ok-500 animate-pulse">
                ● live
              </span>
            )}
          </div>
          <div className="mt-1 flex items-center gap-3 font-mono text-[10px] text-ink-500">
            <span>{b.days_overdue}d overdue</span>
            <span>₹{b.overdue_amount.toLocaleString("en-IN")}</span>
          </div>
          {b.primary_intent && (
            <div className="mt-1">
              <IntentTag intent={b.primary_intent} />
            </div>
          )}
        </div>
      </div>

      <button
        onClick={(e) => {
          e.stopPropagation();
          onCall();
        }}
        disabled={calling || isActiveCall}
        className={`mt-2 w-full rounded px-2 py-1 font-mono text-[10px] uppercase tracking-wider transition ${
          calling
            ? "bg-ink-800 text-ink-500"
            : isActiveCall
              ? "bg-ok-900/30 text-ok-500"
              : "bg-ink-100 text-ink-900 hover:bg-ink-200"
        }`}
      >
        {calling ? "Calling..." : isActiveCall ? "● On call" : "📞 Call now"}
      </button>
    </li>
  );
}

function RiskDot({ tier }: { tier: RiskTier }) {
  const color = {
    low: "bg-emerald-500",
    medium: "bg-amber-500",
    high: "bg-orange-500",
    critical: "bg-red-500",
  }[tier];
  return <span className={`inline-block h-2 w-2 rounded-full ${color}`} />;
}

function IntentTag({ intent }: { intent: string }) {
  const label = {
    hardship: "Hardship",
    distress: "Distress",
    avoidance: "Avoidance",
    cooperative: "Cooperative",
    promise_to_pay: "PTP",
    affordability: "Partial",
    dispute: "Dispute",
  }[intent] ?? intent;

  const tone = {
    distress: "bg-red-900/50 text-red-300",
    hardship: "bg-orange-900/50 text-orange-300",
    avoidance: "bg-amber-900/50 text-amber-300",
    cooperative: "bg-emerald-900/50 text-emerald-300",
    promise_to_pay: "bg-blue-900/50 text-blue-300",
    affordability: "bg-blue-900/50 text-blue-300",
    dispute: "bg-purple-900/50 text-purple-300",
  }[intent] ?? "bg-ink-800 text-ink-400";

  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 font-mono text-[9px] uppercase ${tone}`}
    >
      {label}
    </span>
  );
}