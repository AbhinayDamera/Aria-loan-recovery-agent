# Aria — Compassionate AI Loan Recovery

> Hackvora 2026 submission. An AI voice agent that recovers loans through empathetic, disclosed, multilingual conversation — with real-time emotion monitoring and instant human escalation when needed.

## What it does

Aria is a fintech voice agent that:

- Calls borrowers with overdue EMIs over real telephony (Plivo)
- Speaks fluent Hindi-English code-switch (Sarvam.ai STT + TTS)
- Detects hardship, dispute, distress, and promise-to-pay signals in real time
- Offers EMI restructuring, moratoriums, and partial-payment plans
- Auto-escalates to a human within 5 seconds on distress
- Streams a live emotion graph and tagged transcript to a Next.js dashboard
- Always discloses its AI identity at call start (RBI Fair Practices Code aligned)

## Architecture

```
Borrower phone ↔ Plivo ↔ Pipecat agent ↔ [Sarvam STT, GPT-4o, Sarvam TTS, Analytics]
                                              ↓
                                    Postgres + Redis pub/sub
                                              ↓
                              Live dashboard (Next.js)  /  Human operator
```

See `docs/architecture.png` for the full diagram.

## Repo structure

```
aria/
├── agent/                  Python · Pipecat voice agent + FastAPI server
│   └── app/
│       ├── main.py         FastAPI + Plivo webhooks + WebSocket bridge
│       ├── pipeline.py     Pipecat pipeline factory
│       ├── conversation.py System prompt + dialog state
│       ├── intent_extractor.py  Structured PTP/hardship/distress detection
│       ├── emotion.py      Acoustic + semantic emotion scoring
│       ├── sarvam_service.py    Custom Pipecat services for Sarvam.ai
│       ├── events.py       Redis pub/sub publisher
│       ├── db.py           SQLAlchemy models
│       └── config.py       Environment config
├── web/                    Next.js dashboard (App Router + Tailwind)
│   ├── app/                Pages
│   ├── components/         LiveCallCard, TranscriptView, EmotionChart, MetricTile
│   └── lib/                WebSocket client + shared types
├── docker-compose.yml      Postgres + Redis (local dev)
├── .env.example            Copy to .env.local; fill in API keys
└── README.md               You are here
```

## Prerequisites

- Python 3.10+ (`uv` recommended for dep management)
- Node.js 20+ and pnpm (or npm)
- Docker (for local Postgres + Redis)
- API keys: OpenAI, Sarvam.ai, Plivo
- ngrok or Cloudflare Tunnel (to expose Plivo webhook from localhost)

## Getting started

### 1. Clone + env

```bash
cp .env.example .env.local
# Fill in API keys
```

### 2. Start services

```bash
docker compose up -d  # Postgres on 5432, Redis on 6379
```

### 3. Run the agent

```bash
cd agent
uv sync                        # or: pip install -e .
uv run uvicorn app.main:app --reload --port 8000
```

In another terminal, expose to Plivo:

```bash
ngrok http 8000
# Copy the https URL into your Plivo Application's Answer URL
```

### 4. Run the dashboard

```bash
cd web
pnpm install
pnpm dev   # http://localhost:3000
```

### 5. Place a test call

From the Plivo console, place an outbound call to your test number using the Application you configured. The dashboard will show the live transcript, emotion graph, and intent tags.

## Sprint tracks

- **Track A (voice/AI):** Hours 2–8 → core voice loop in browser. Hours 8–16 → telephony + intent. Hours 16–24 → emotion + escalation.
- **Track B (full-stack):** Hours 2–8 → dashboard shell. Hours 8–16 → live transcript + emotion chart. Hours 16–24 → operator handoff UI + call list.

See sprint plan in the team chat for hour-by-hour breakdown.

## Demo backup

If telephony fails on stage, flip `DEMO_MODE=browser` in `.env.local` and restart the agent — it falls back to mic/speaker over WebRTC, and the dashboard works identically.

## Compliance notes

- Aria opens every call with: *"Hi, I'm Aria, an AI assistant from <Lender>. This call may be recorded for quality. Is now a good time to talk?"*
- Borrower can say "stop calling me" at any time → DNC list, immediate hangup
- All transcripts hashed (SHA-256) for audit trail
- Distress detection auto-escalates to human; threshold configurable in `config.py`

## Team

- TODO: Add team members + roles before submission lock
