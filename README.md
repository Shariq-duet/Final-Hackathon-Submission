# 🎮 Game Debugger — Agentic Multi-Source Bug Triage System

> **Built on Google Antigravity** | Deployed on Google Cloud Run | Gemini 2.5 Flash via Vertex AI

A production-grade, 3-phase agentic AI pipeline that ingests community bug reports from **multiple simultaneous sources**, extracts meaningful insights, detects contradictions across sources, generates a prioritized action chain, simulates execution with visible state changes, and recovers from partial failures — all with live streaming telemetry via Mission Control.

---

## 🏗️ Architecture Overview

```
  ┌──────────────────────────────────────────────────────────────────┐
  │                        INPUT SOURCES (5 types)                   │
  │  Discord API  │  CSV Upload  │  TXT Upload  │  Local Logs │ Demo  │
  └───────────────────────────────┬──────────────────────────────────┘
                                  │
                                  ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │              PHASE 1: INGESTION — ingestion_agent.py             │
  │  Gemini 2.5 Flash (Vertex AI) · Temperature 0.0                  │
  │  · Parses raw multi-source content into structured LogEntry JSON  │
  │  · Extracts: username, timestamp, category, message, media_url    │
  │  · Enforced via Pydantic schema (LogEntry / IngestedLogs)         │
  └───────────────────────────────┬──────────────────────────────────┘
                                  │
                                  ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │           PHASE 2: CLUSTERING + CONTRADICTION DETECTION          │
  │              clustering_agent.py — Gemini 2.5 Flash              │
  │  · Clusters bug reports into IncidentReports by failure type      │
  │  · Filters noise (social, off-topic, duplicate, spam)             │
  │  · DETECTS CONTRADICTIONS: conflicting claims across sources      │
  │  · Scores source credibility by recency + specificity             │
  │  · Proposes resolution paths for contradictions                   │
  └───────────────────────────────┬──────────────────────────────────┘
                                  │
                                  ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │              PHASE 3: EXECUTION PLAN — execution_agent.py        │
  │  Gemini 2.5 Flash · Temperature 0.7                               │
  │  · Ranks 3–5 incidents by severity (Critical first)               │
  │  · Generates: Jira ticket, Discord announcement, code patch       │
  │  · Applies constraints: rate limits, budget, policy rules         │
  │  · Retry logic + rollback for failed API calls                    │
  │  · Emits BEFORE/AFTER state with cost + latency metrics           │
  └───────────────────────────────┬──────────────────────────────────┘
                                  │
                        Human-in-the-Loop Approval
                        (Web Dashboard + Mobile App)
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
              Jira REST API             Discord Webhook
           (Bug Tickets + Patches)   (Public Announcements)
```

---

## 🔑 Google Antigravity Integration (Mandatory Requirement)

This system is **orchestrated entirely by Google Antigravity**. Antigravity drives:

| Antigravity Role | How It's Used |
|---|---|
| **Agent Orchestration** | Plans and runs all 3 pipeline phases as sequential agentic steps |
| **Tool / API Integration** | Calls Discord API, Jira REST API, Discord Webhook via structured tool use |
| **Workplan + Task Tracking** | `implementation_plan.md` and `task.md` generated and updated by Antigravity |
| **Decision Trace** | Full reasoning chain emitted as structured telemetry events to Mission Control |
| **Action Execution** | Each webhook call is an Antigravity-directed action with retry + rollback |
| **Recovery Steps** | Antigravity detects failures, logs rollback state, and continues pipeline |
| **Trace Logs** | `ANTIGRAVITY_TRACE_LOG.md` contains the full agent decision trace |

The backend Python agents are the **execution layer** — all orchestration decisions, reasoning chains, and action sequencing are driven by Antigravity's agentic loop.

---

## 📡 Input Sources (5 Types — Rubric Requirement)

| # | Source Type | Format | How Ingested |
|---|---|---|---|
| 1 | **Discord Live Feed** | Unstructured text + media | Discord REST API via `/analyze-discord` |
| 2 | **CSV Issue Tracker** | Structured rows (QA, Support) | `/analyze-csv` endpoint |
| 3 | **TXT Report Upload** | Semi-structured text | `/analyze-upload` endpoint |
| 4 | **Local Mock Logs** | Multi-file unstructured text | `/analyze-local` endpoint |
| 5 | **Real-time Demo Feed** | Simulated live stream | `/analyze-demo` endpoint |

All sources flow into the same Phase 1 ingestion agent, producing a unified `LogEntry[]` JSON array regardless of source type.

---

## ⚠️ Contradiction Detection

The Phase 2 clustering agent actively searches for **conflicting claims** across sources:

**Example from live run:**
> - **Claim A:** QA Internal Log (2026-05-19 09:30): *"Plasma rifle crash confirmed FIXED in build 2.1.4"*
> - **Claim B:** Discord (2026-05-19 13:54): *"Plasma rifle still crashing every time in Neon District on build 2.1.4"*
>
> **Credibility verdict:** Discord report is more credible — newer timestamp (+4 hours), corroborated by 8 additional players, includes specific reproduction path (Neon District + equip action).
>
> **Resolution path:** Reproduce in staging using production build 2.1.4 on Neon District map. Compare crash signatures against QA test environment config.

Each contradiction produces a `ContradictionReport` with:
- `topic` — the system/bug in dispute
- `claim_a` / `claim_b` — the conflicting claims with attribution
- `credibility_verdict` — scored by recency, specificity, corroboration count
- `resolution_path` — concrete investigation action

---

## ⛓️ Action Chain (3–5 Connected Actions)

For each Critical incident, the system executes a connected 4-step chain:

```
1. DIAGNOSE    → AI generates root-cause analysis + implication report
2. NOTIFY DEV  → Jira ticket created with P0 priority + AI code patch
3. NOTIFY COMM → Discord public announcement (Critical severity only)
4. ROLLBACK    → If API fails, ticket saved locally + next run scheduled
```

Constraints enforced per run:
- `MAX_DISCORD_ANNOUNCEMENTS = 3` — prevents spam, excess skipped and logged
- `TIMEOUT = 5s` per API call — rate-limit protection
- `MAX_RETRY = 2` per action before rollback

---

## 🔄 Failure Recovery & Rollback

The system handles 3 failure scenarios with visible telemetry:

| Failure Type | Recovery Action | Telemetry Tag |
|---|---|---|
| API timeout (attempt 1) | Retry after 3s | `[WARNING]` |
| Permanent API failure (2 attempts) | Save locally, continue pipeline | `[ERROR]` + `[WARNING] ROLLBACK` |
| Rate limit constraint hit | Skip + schedule for next run | `[REASONING] CONSTRAINT ENFORCED` |

---

## 📊 Before vs. After State (Outcome Visualization)

Every execution concludes with a measurable outcome summary:

```
BEFORE STATE: 4 incidents queued | 0 Jira tickets | 0 Discord announcements

... (execution with retry, rollback, constraint enforcement) ...

AFTER STATE — EXECUTION OUTCOME:
  ✅ Jira tickets created:        3/4
  ✅ Discord announcements sent:  2
  ❌ Failed actions (rolled back): 1
  ⏱️  Total execution time:       28.4s
  💰 Estimated action cost:      $0.10 USD
  📋 Rolled-back items saved locally: 1
```

---

## 🚀 Live Deployment

| Component | URL |
|---|---|
| **Backend API** | `https://community-ai-backend-631639319596.us-central1.run.app` |
| **Web Dashboard** | `https://community-ai-backend-631639319596.us-central1.run.app/` |
| **Health Check** | `https://community-ai-backend-631639319596.us-central1.run.app/health` |
| **GCP Project** | `gen-lang-client-0583565763` |
| **Region** | `us-central1` |

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Mission Control web dashboard |
| `GET` | `/health` | Service health & uptime |
| `POST` | `/analyze-upload` | Upload `.txt` log file → pipeline |
| `POST` | `/analyze-csv` | Upload `.csv` structured data → pipeline |
| `POST` | `/analyze-local` | Run pipeline on `mock_discord_logs/` |
| `POST` | `/analyze-discord` | Fetch live Discord messages → pipeline |
| `POST` | `/analyze-demo` | Simulated demo (no AI calls needed) |
| `GET` | `/stream/{job_id}` | SSE live telemetry stream |
| `GET` | `/result/{job_id}` | Poll for final execution plan |
| `POST` | `/execute` | Human-approved — dispatch webhooks |

---

## 📁 Project Structure

```
AiSeekhoClean/
├── server.py                    # FastAPI server — all HTTP endpoints & SSE streaming
├── ingestion_agent.py           # Phase 1: Multi-source fetch + Vertex AI log parsing
├── clustering_agent.py          # Phase 2: Clustering + Contradiction detection
├── execution_agent.py           # Phase 3: Execution plan + retry/rollback webhook dispatch
├── telemetry.py                 # In-memory job store + SSE event emitter
├── generate_data.py             # Mock data generator for Discord testing
├── get-discord-messages.py      # Standalone Discord fetch + Gemini extraction script
├── requirements.txt             # Python dependencies
├── Procfile                     # Cloud Run process definition
├── mock_discord_logs/
│   ├── *.txt                    # Local mock Discord logs (unstructured)
│   └── known_issues_tracker.csv # Structured CSV: QA + Support + Telemetry data
├── static/
│   └── index.html               # Mission Control web dashboard (single-file SPA)
└── ANTIGRAVITY_TRACE_LOG.md     # Full Antigravity agent decision trace
```

---

## ⚙️ Environment Variables

```env
# Google Cloud / Vertex AI
GOOGLE_CLOUD_PROJECT=gen-lang-client-0583565763

# Discord Bot (live message ingestion)
DISCORD_BOT_TOKEN=your-discord-bot-token
DISCORD_CHANNEL_ID=your-bug-report-channel-id

# Jira Integration
JIRA_WEBHOOK_URL=https://your-domain.atlassian.net/rest/api/3/issue
JIRA_EMAIL=your@email.com
JIRA_API_TOKEN=your-jira-api-token
JIRA_PROJECT_KEY=BUG

# Discord Webhook (public announcements)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_URL_BUG=https://discord.com/api/webhooks/...  # bug-report channel
```

---

## 🛠️ Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python -m uvicorn server:app --host 0.0.0.0 --port 8080 --reload

# Open dashboard
# http://localhost:8080
```

---

## 📦 Deploy to Google Cloud Run

```bash
gcloud run deploy community-ai-backend \
  --source . \
  --region us-central1 \
  --allow-unauthenticated
```

---

## 📱 Mobile App

React Native Android companion app (`Game/gameDebugger-main/`):

- 📁 Upload `.txt` / `.csv` files from phone storage
- ⚡ Live Discord ingestion trigger
- 🎭 Demo mode for presentations
- 📡 Real-time SSE telemetry feed with color-coded event types
- 📋 Expandable incident cards with Jira tickets & AI code patches
- ✅ Human-in-the-Loop approval + webhook dispatch

**Build APK:**
```bash
cd Game/gameDebugger-main/android
.\gradlew.bat assembleDebug
# Output: android/app/build/outputs/apk/debug/app-debug.apk
```

---

## 🧠 AI Models & Configuration

| Phase | Model | Temp | Purpose |
|---|---|---|---|
| Phase 1 Ingestion | Gemini 2.5 Flash (Vertex AI) | 0.0 | Deterministic structured extraction |
| Phase 2 Clustering | Gemini 2.5 Flash (Vertex AI) | 0.0 | Deterministic classification + contradiction scoring |
| Phase 3 Execution | Gemini 2.5 Flash (Vertex AI) | 0.7 | Creative but grounded code patches |

All phases use **Pydantic schema enforcement** via `response_schema` to guarantee valid structured JSON output. Retry-with-backoff (`telemetry.retry_with_backoff`) wraps every Vertex AI call.

---

## 🔌 Integrations

| Integration | Purpose | Auth Method |
|---|---|---|
| **Discord Bot API** | Ingest live community bug reports | Bot token |
| **Discord Webhook** | Post public bug announcements | Webhook URL |
| **Jira REST API v3** | Auto-create prioritized bug tickets | Email + API Token |
| **Google Vertex AI** | Run Gemini 2.5 Flash agents | GCP Service Account |
| **Google Cloud Run** | Serverless deployment | gcloud CLI |

---

## 💰 Cost & Latency Analysis

| Operation | Estimated Latency | Estimated Cost |
|---|---|---|
| Phase 1 Ingestion (50 msgs) | 8–15s | ~$0.003 |
| Phase 2 Clustering | 10–18s | ~$0.005 |
| Phase 3 Execution Plan | 12–20s | ~$0.008 |
| Jira ticket POST | 1–2s | Free tier |
| Discord webhook POST | <1s | Free |
| **Full pipeline (end-to-end)** | **35–60s** | **~$0.016–0.02** |

Cloud Run: ~$0.00002400 per vCPU-second. Typical run: 60s × 1 vCPU = **~$0.0014** compute cost.

---

## 📈 Baseline Comparison

| Capability | Traditional Rule-Based System | This System |
|---|---|---|
| Input types | 1 (usually a fixed form) | 5 (Discord, CSV, TXT, local, real-time) |
| Insight extraction | Keyword matching | LLM semantic understanding |
| Contradiction detection | ❌ Not possible | ✅ Automatic with credibility scoring |
| Noise filtering | Static blocklist | AI-based semantic filtering |
| Action chain | Single pre-defined webhook | 3–5 dynamic, severity-ranked actions |
| Failure recovery | Crash or silent failure | Retry → rollback → local save |
| Outcome visibility | None | Before/after state + cost + latency |
| Human approval | ❌ | ✅ Human-in-the-loop gate |

---

## ⚠️ Assumptions & Constraints

- Discord messages are in English
- Jira project must have a "Bug" issue type configured
- Vertex AI quota: ~60 RPM on Gemini 2.5 Flash; pipeline auto-retries on 429
- Cloud Run memory: 512MB minimum recommended (Pydantic schema parsing)
- MAX 50 Discord messages per ingestion run (configurable via `limit` param)
- Demo mode does NOT make real AI or API calls — suitable for offline presentations

---

## ⚠️ Limitations

- No persistent database — telemetry events are in-memory (lost on restart)
- CSV input assumes UTF-8 encoding with a header row
- Contradiction detection quality depends on source diversity — works best with 3+ sources
- Code patches are AI-generated simulations, not tested against actual game codebase

---

## 🤝 Built With

- **Google Antigravity** — Agent orchestration, reasoning, and task planning
- **Google Vertex AI** — Gemini 2.5 Flash for all 3 agent phases
- **Google Cloud Run** — Serverless deployment
- **FastAPI** — Backend API + SSE streaming
- **Pydantic** — Structured AI output schema enforcement
- **React Native** — Android mobile companion app
- **Discord REST API** — Live community data ingestion
- **Jira REST API v3** — Bug ticket automation
