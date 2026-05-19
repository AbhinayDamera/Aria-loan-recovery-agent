// Mirrors agent/app/events.py and aria_* tables · keep in sync.

// ─── Live event stream ─────────────────────────────────────

export type EventType =
  | "call_started"
  | "call_ended"
  | "transcript"
  | "intent"
  | "emotion"
  | "ptp_captured"
  | "escalation"
  | "agent_state";

export type AriaEvent = {
  type: EventType;
  call_id: string;
  timestamp: number;
  payload: Record<string, unknown>;
};

export type IntentType =
  | "promise_to_pay"
  | "hardship"
  | "affordability"
  | "dispute"
  | "distress"
  | "avoidance"
  | "cooperative"
  | "none";

export type TranscriptTurn = {
  role: "aria" | "borrower";
  text: string;
  intent?: IntentType;
  ts: number;
};

export type EmotionPoint = { t: number; score: number };


// ─── Borrowers (from Supabase) ─────────────────────────────

export type RiskTier = "low" | "medium" | "high" | "critical";

export type BorrowerStatus =
  | "pending"
  | "contacted"
  | "ptp"
  | "escalated"
  | "resolved"
  | "dnc";

export type Borrower = {
  id: string;
  name: string;
  phone: string;
  language_pref: string;
  location: string;

  loan_principal: number;
  emi_amount: number;
  tenure_months: number;
  tenure_remaining_months: number;

  days_overdue: number;
  overdue_amount: number;
  total_outstanding: number;

  risk_score: number;
  risk_tier: RiskTier;
  status: BorrowerStatus;
  primary_intent: string | null;
  last_contacted_at: string | null;

  created_at: string;
  updated_at?: string;
};


// ─── Past calls ────────────────────────────────────────────

export type PastCall = {
  id: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  outcome: string | null;
  intent_detected: string | null;
  distress_peak: number;
  personality_modes_used: string[] | null;
  escalated: boolean;
  ptp_amount: number | null;
  ptp_date: string | null;
  ptp_kept: boolean | null;
  summary: string | null;
  promises_made: string[] | null;
  concerns_raised: string[] | null;
};


// ─── Payments ──────────────────────────────────────────────

export type PaymentStatus = "paid" | "missed" | "overdue" | "upcoming";

export type Payment = {
  id: number;
  due_date: string;
  paid_date: string | null;
  amount: number;
  status: PaymentStatus;
};


// ─── Stats ─────────────────────────────────────────────────

export type Stats = {
  calls_today: number;
  ptps_today: number;
  escalations_today: number;
  avg_duration_seconds: number;
  queue_total: number;
  queue_critical: number;
  queue_high: number;
  queue_hardship: number;
  total_overdue_amount: number;
  ptp_rate_30d: number;
  compliance_violations: number;
};
