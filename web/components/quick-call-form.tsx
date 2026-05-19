"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Props = {
  onCallTriggered?: (callSid: string, name: string) => void;
};

export function QuickCallForm({ onCallTriggered }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [calling, setCalling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Form fields
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("+91");
  const [daysOverdue, setDaysOverdue] = useState("12");
  const [overdueAmount, setOverdueAmount] = useState("4500");
  const [emiAmount, setEmiAmount] = useState("4500");
  const [language, setLanguage] = useState("en-in");

  const reset = () => {
    setName("");
    setPhone("+91");
    setDaysOverdue("12");
    setOverdueAmount("4500");
    setEmiAmount("4500");
    setLanguage("en-in");
    setError(null);
    setSuccess(null);
  };

  const handleCall = async () => {
    setError(null);
    setSuccess(null);

    if (!name.trim() || !phone.trim() || phone.trim() === "+91") {
      setError("Name and phone are required");
      return;
    }

    setCalling(true);
    try {
      const res = await fetch(`${API_BASE}/api/quick-call`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          phone: phone.trim(),
          days_overdue: parseInt(daysOverdue) || 5,
          overdue_amount: parseInt(overdueAmount) || 4500,
          emi_amount: parseInt(emiAmount) || 4500,
          language_pref: language,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        const hint = data.hint ? ` (${data.hint})` : "";
        setError(`${data.error || "Call failed"}${hint}`);
        setCalling(false);
        return;
      }

      setSuccess(`📞 Calling ${data.borrower_name}...`);
      onCallTriggered?.(data.call_sid, data.borrower_name);

      // Reset after a delay
      setTimeout(() => {
        reset();
        setCalling(false);
      }, 3000);
    } catch (e) {
      setError(`Network error: ${e}`);
      setCalling(false);
    }
  };

  return (
    <div className="border-t border-ink-700">
      {/* Header / toggle */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-3 py-2 text-left transition hover:bg-ink-900/50"
      >
        <span className="font-mono text-[10px] uppercase tracking-wider text-ink-400">
          ⚡ Quick call
        </span>
        <span className="font-mono text-[10px] text-ink-500">
          {expanded ? "▼" : "▶"}
        </span>
      </button>

      {/* Form */}
      {expanded && (
        <div className="space-y-2 border-t border-ink-800 bg-ink-900/30 p-3">
          <Input
            label="Name"
            value={name}
            onChange={setName}
            placeholder="Asha Kumari"
            disabled={calling}
          />
          <Input
            label="Phone"
            value={phone}
            onChange={setPhone}
            placeholder="+919876543210"
            disabled={calling}
          />

          <div className="grid grid-cols-2 gap-2">
            <Input
              label="Days overdue"
              value={daysOverdue}
              onChange={setDaysOverdue}
              placeholder="12"
              type="number"
              disabled={calling}
            />
            <Input
              label="Overdue ₹"
              value={overdueAmount}
              onChange={setOverdueAmount}
              placeholder="4500"
              type="number"
              disabled={calling}
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <Input
              label="EMI ₹"
              value={emiAmount}
              onChange={setEmiAmount}
              placeholder="4500"
              type="number"
              disabled={calling}
            />
            <div>
              <div className="font-mono text-[9px] uppercase tracking-wider text-ink-500 mb-0.5">
                Language
              </div>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                disabled={calling}
                className="w-full rounded border border-ink-700 bg-ink-900 px-2 py-1 text-xs text-ink-200 focus:border-ink-500 focus:outline-none disabled:opacity-50"
              >
                <option value="en-in">English</option>
                <option value="hi-en">Hindi-English</option>
                <option value="te-en">Telugu-English</option>
                <option value="ta-en">Tamil-English</option>
              </select>
            </div>
          </div>

          {error && (
            <div className="rounded border border-signal-400/40 bg-signal-400/10 px-2 py-1 text-[11px] text-signal-400">
              {error}
            </div>
          )}
          {success && (
            <div className="rounded border border-ok-500/40 bg-ok-900/30 px-2 py-1 text-[11px] text-ok-500">
              {success}
            </div>
          )}

          <button
            onClick={handleCall}
            disabled={calling}
            className="w-full rounded bg-ink-100 px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-900 transition hover:bg-ink-200 disabled:opacity-50"
          >
            {calling ? "📞 Calling..." : "📞 Call now"}
          </button>
        </div>
      )}
    </div>
  );
}


function Input({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  disabled,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  disabled?: boolean;
}) {
  return (
    <div>
      <div className="font-mono text-[9px] uppercase tracking-wider text-ink-500 mb-0.5">
        {label}
      </div>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="w-full rounded border border-ink-700 bg-ink-900 px-2 py-1 text-xs text-ink-200 placeholder:text-ink-600 focus:border-ink-500 focus:outline-none disabled:opacity-50"
      />
    </div>
  );
}