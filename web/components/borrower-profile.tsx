"use client";

import { useEffect, useState } from "react";
import type { Borrower, PastCall, Payment } from "@/lib/types";
import {
  callBorrower,
  getBorrower,
  getBorrowerCalls,
  getBorrowerPayments,
} from "@/lib/api";
import { PaymentTimeline } from "./payment-timeline";
import { CallHistory } from "./call-history";

type Props = {
  borrowerId: string;
  onCallTriggered?: () => void;
};

export function BorrowerProfile({ borrowerId, onCallTriggered }: Props) {
  const [b, setB] = useState<Borrower | null>(null);
  const [calls, setCalls] = useState<PastCall[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(true);
  const [calling, setCalling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      getBorrower(borrowerId),
      getBorrowerCalls(borrowerId),
      getBorrowerPayments(borrowerId),
    ])
      .then(([borrower, callRes, payRes]) => {
        setB(borrower);
        setCalls(callRes.calls);
        setPayments(payRes.payments);
        setLoading(false);
      })
      .catch((e) => {
        setError(String(e));
        setLoading(false);
      });
  }, [borrowerId]);

  const handleCall = async () => {
    setCalling(true);
    try {
      await callBorrower(borrowerId);
      onCallTriggered?.();
    } catch (e) {
      setError(`Call failed: ${e}`);
    } finally {
      setTimeout(() => setCalling(false), 2000);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-32 rounded-lg border border-ink-700 bg-ink-900/30 animate-pulse" />
        <div className="h-40 rounded-lg border border-ink-700 bg-ink-900/30 animate-pulse" />
        <div className="h-60 rounded-lg border border-ink-700 bg-ink-900/30 animate-pulse" />
      </div>
    );
  }

  if (error || !b) {
    return (
      <div className="rounded-lg border border-signal-400/40 px-4 py-6 text-sm text-signal-400">
        {error ?? "Borrower not found"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Profile header */}
      <div className="rounded-lg border border-ink-700 px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h2 className="text-2xl font-medium text-ink-100">{b.name}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-ink-400">
              <span>{b.phone}</span>
              <span>•</span>
              <span>{b.location}</span>
              <span>•</span>
              <span className="font-mono text-xs uppercase">
                {b.language_pref}
              </span>
            </div>
          </div>
          <RiskBadge tier={b.risk_tier} score={b.risk_score} />
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Loan principal" value={`₹${b.loan_principal.toLocaleString("en-IN")}`} />
          <Stat label="EMI" value={`₹${b.emi_amount.toLocaleString("en-IN")}`} />
          <Stat label="Days overdue" value={`${b.days_overdue}d`} tone={b.days_overdue > 14 ? "danger" : "warn"} />
          <Stat label="Overdue amount" value={`₹${b.overdue_amount.toLocaleString("en-IN")}`} tone="warn" />
          <Stat label="Tenure remaining" value={`${b.tenure_remaining_months} mo`} />
          <Stat label="Total outstanding" value={`₹${b.total_outstanding.toLocaleString("en-IN")}`} />
          <Stat label="Status" value={prettyStatus(b.status)} />
          <Stat label="Last contacted" value={b.last_contacted_at ? relativeTime(b.last_contacted_at) : "Never"} />
        </div>

        <button
          onClick={handleCall}
          disabled={calling || b.status === "dnc"}
          className="mt-5 w-full rounded-md bg-ink-100 px-4 py-2.5 font-mono text-xs uppercase tracking-wider text-ink-900 transition hover:bg-ink-200 disabled:opacity-50"
        >
          {calling ? "📞 Calling…" : `📞 Call ${b.name.split(" ")[0]} now`}
        </button>
      </div>

      {/* Payment timeline */}
      <div className="rounded-lg border border-ink-700 px-5 py-4">
        <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-ink-500">
          Payment timeline
        </h3>
        <PaymentTimeline payments={payments} />
      </div>

      {/* Call history */}
      <div className="rounded-lg border border-ink-700 px-5 py-4">
        <h3 className="mb-3 font-mono text-xs uppercase tracking-wider text-ink-500">
          Call history ({calls.length})
        </h3>
        <CallHistory calls={calls} />
      </div>
    </div>
  );
}


function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "warn" | "danger";
}) {
  const valueClass =
    tone === "danger"
      ? "text-signal-400"
      : tone === "warn"
        ? "text-amber-400"
        : "text-ink-100";
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-wider text-ink-500">
        {label}
      </div>
      <div className={`mt-0.5 text-base font-medium ${valueClass}`}>{value}</div>
    </div>
  );
}

function RiskBadge({ tier, score }: { tier: string; score: number }) {
  const cls = {
    low: "border-emerald-500/40 bg-emerald-900/30 text-emerald-300",
    medium: "border-amber-500/40 bg-amber-900/30 text-amber-300",
    high: "border-orange-500/40 bg-orange-900/30 text-orange-300",
    critical: "border-red-500/40 bg-red-900/30 text-red-300",
  }[tier] ?? "border-ink-700 bg-ink-900 text-ink-400";

  return (
    <div className={`shrink-0 rounded-md border px-3 py-1.5 ${cls}`}>
      <div className="font-mono text-[10px] uppercase tracking-wider opacity-70">
        Risk
      </div>
      <div className="text-sm font-semibold uppercase">
        {tier} · {score}
      </div>
    </div>
  );
}

function prettyStatus(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function relativeTime(iso: string): string {
  const t = new Date(iso).getTime();
  const diff = (Date.now() - t) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}
