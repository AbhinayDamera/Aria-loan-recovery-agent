"use client";

import type { Payment } from "@/lib/types";

type Props = {
  payments: Payment[];
};

export function PaymentTimeline({ payments }: Props) {
  if (payments.length === 0) {
    return (
      <div className="text-xs text-ink-500">No payment history yet.</div>
    );
  }

  // Reverse so oldest is on the left
  const ordered = [...payments].reverse();

  return (
    <div>
      <div className="flex items-end gap-1">
        {ordered.map((p) => (
          <PaymentBar key={p.id} payment={p} />
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-3 font-mono text-[10px] text-ink-500">
        <Legend color="bg-ok-500" label="Paid" />
        <Legend color="bg-amber-500" label="Missed" />
        <Legend color="bg-signal-400" label="Overdue" />
        <Legend color="bg-ink-700" label="Upcoming" />
      </div>
    </div>
  );
}

function PaymentBar({ payment }: { payment: Payment }) {
  const color = {
    paid: "bg-ok-500",
    missed: "bg-amber-500",
    overdue: "bg-signal-400",
    upcoming: "bg-ink-700",
  }[payment.status];

  const date = new Date(payment.due_date);
  const month = date.toLocaleString("en-IN", { month: "short" });

  return (
    <div className="group flex flex-1 flex-col items-center gap-1 min-w-0">
      <div
        className={`h-12 w-full rounded-sm ${color} relative cursor-help`}
        title={`${payment.status.toUpperCase()} · Due ${payment.due_date} · ₹${payment.amount.toLocaleString("en-IN")}`}
      >
        {payment.status === "missed" || payment.status === "overdue" ? (
          <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-white">
            !
          </span>
        ) : null}
      </div>
      <div className="font-mono text-[9px] uppercase text-ink-500">{month}</div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`inline-block h-2 w-2 rounded-sm ${color}`} />
      {label}
    </span>
  );
}
