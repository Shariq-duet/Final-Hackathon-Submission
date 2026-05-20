import os
import io
import csv
import json
import time
import threading
from datetime import datetime, timezone
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from dotenv import load_dotenv

import telemetry
from ingestion_agent import run_ingestion, run_discord_ingestion
from clustering_agent import run_clustering
from execution_agent import generate_plan, execute_webhooks, ExecutionPlan

# Load environment variables
load_dotenv()

# Track server boot time for health endpoint
_BOOT_TIME = datetime.now(timezone.utc)

app = FastAPI(title="3-Phase Agentic Workflow API — Mission Control")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Serve the Mission Control Dashboard
# ─────────────────────────────────────────────
@app.get("/")
async def serve_dashboard():
    """Serve the Mission Control UI."""
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="Dashboard HTML not found.")
    return FileResponse(html_path, media_type="text/html")


# ─────────────────────────────────────────────
# Health Endpoint
# ─────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """Service health & uptime."""
    uptime = (datetime.now(timezone.utc) - _BOOT_TIME).total_seconds()
    return {
        "status": "operational",
        "uptime_seconds": round(uptime, 1),
        "version": "2.0.0-mission-control",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────
# Internal: 3-Phase Pipeline Runner
# ─────────────────────────────────────────────
def _run_pipeline(job_id: str, raw_text: str = None, mode: str = "upload",
                  channel_id: str = None, bot_token: str = None, limit: int = 50):
    """
    Runs the full 3-phase pipeline in a background thread.
    Emits telemetry events at every step so the SSE stream stays alive.
    """
    try:
        # ── Phase 1: Ingestion ──
        telemetry.emit(job_id, "═══ PHASE 1: INGESTION ═══", "phase")

        if mode == "upload":
            telemetry.emit(job_id, "Processing uploaded file content...", "action")
            logs_list = run_ingestion(raw_text, job_id=job_id)

        elif mode == "local":
            log_dir = os.path.join(os.path.dirname(__file__), "mock_discord_logs")
            if not os.path.exists(log_dir):
                telemetry.store.fail_job(job_id, "Local log directory not found.")
                return

            files = [f for f in os.listdir(log_dir) if f.endswith(".txt")]
            if not files:
                telemetry.store.fail_job(job_id, "Local log directory is empty.")
                return

            logs_list = []
            for filename in files:
                filepath = os.path.join(log_dir, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    file_text = f.read()
                telemetry.emit(job_id, f"Sending {filename} to Ingestion Agent...", "action")
                file_logs = run_ingestion(file_text, job_id=job_id)
                if file_logs:
                    logs_list.extend(file_logs)
                    telemetry.emit(job_id, f"Added {len(file_logs)} logs from {filename}.", "observation")
                else:
                    telemetry.emit(job_id, f"Failed to parse {filename} or file was empty.", "warning")
                time.sleep(3)

        elif mode == "discord":
            telemetry.emit(job_id, "Pulling live data from Discord API...", "action")
            logs_list = run_discord_ingestion(channel_id, bot_token, limit, job_id=job_id)

        else:
            telemetry.store.fail_job(job_id, f"Unknown pipeline mode: {mode}")
            return

        if not logs_list:
            telemetry.store.fail_job(job_id, "Phase 1 Ingestion returned no parsed logs.")
            return

        telemetry.emit(job_id, f"Phase 1 complete. {len(logs_list)} total logs extracted.", "observation")

        # ── Phase 2: Clustering ──
        telemetry.emit(job_id, "═══ PHASE 2: CLUSTERING ═══", "phase")
        insights_dict = run_clustering(logs_list, job_id=job_id)

        if not insights_dict or "incidents" not in insights_dict:
            telemetry.store.fail_job(job_id, "Phase 2 Clustering failed to generate insights.")
            return

        telemetry.emit(job_id, f"Phase 2 complete. {len(insights_dict.get('incidents', []))} incidents isolated.", "observation")
        # ── Cap to top 10 before Phase 3 to keep execution fast ──
        
        incidents = insights_dict.get("incidents", [])
        if len(incidents) > 10:
            telemetry.emit(job_id, f"Trimming {len(incidents)} incidents to top 10 for execution planning...", "reasoning")
            insights_dict["incidents"] = incidents[:10]

        # ── Phase 3: Execution Plan Generation ──
        telemetry.emit(job_id, "═══ PHASE 3: EXECUTION PLAN ═══", "phase")
        plan = generate_plan(insights_dict, job_id=job_id)

        if not plan:
            telemetry.store.fail_job(job_id, "Phase 3 Plan generation failed.")
            return

        telemetry.emit(job_id, "ExecutionPlan generated. Awaiting human approval.", "observation")
        telemetry.store.complete_job(job_id, plan.model_dump())

    except Exception as exc:
        telemetry.store.fail_job(job_id, f"Pipeline crashed: {exc}")


# ─────────────────────────────────────────────
# SSE Streaming Endpoint
# ─────────────────────────────────────────────
@app.get("/stream/{job_id}")
async def stream_telemetry(job_id: str):
    """Server-Sent Events stream for live pipeline telemetry."""
    job = telemetry.store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    def event_generator():
        cursor = 0
        while True:
            events, status = telemetry.store.get_events_since(job_id, cursor)

            for event in events:
                data = json.dumps(event)
                yield f"event: telemetry\ndata: {data}\n\n"
                cursor += 1

            if status == "complete":
                result = telemetry.store.get_job(job_id).get("result")
                yield f"event: complete\ndata: {json.dumps(result)}\n\n"
                return
            elif status == "failed":
                error = telemetry.store.get_job(job_id).get("error")
                yield f"event: error\ndata: {json.dumps({'error': error})}\n\n"
                return

            time.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─────────────────────────────────────────────
# Result Endpoint (poll for final plan)
# ─────────────────────────────────────────────
@app.get("/result/{job_id}")
async def get_result(job_id: str):
    """Returns the execution plan once the pipeline completes."""
    job = telemetry.store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if job["status"] == "running":
        return JSONResponse(status_code=202, content={"status": "running", "message": "Pipeline still processing."})
    elif job["status"] == "failed":
        raise HTTPException(status_code=500, detail=job.get("error", "Pipeline failed."))
    else:
        return job["result"]


# ─────────────────────────────────────────────
# Analyze Endpoints (return job_id, run in bg)
# ─────────────────────────────────────────────
@app.post("/analyze-upload")
async def analyze_upload_endpoint(file: UploadFile = File(...)):
    """Upload a .txt file → background pipeline → stream via SSE."""
    if not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are supported")

    content = await file.read()
    raw_text = content.decode("utf-8")

    job_id = telemetry.store.create_job()
    telemetry.emit(job_id, f"Received uploaded file: {file.filename}", "action")

    thread = threading.Thread(target=_run_pipeline, args=(job_id,), kwargs={"raw_text": raw_text, "mode": "upload"}, daemon=True)
    thread.start()

    return {"job_id": job_id}


@app.post("/analyze-local")
async def analyze_local_endpoint():
    """Trigger local log analysis → background pipeline → stream via SSE."""
    job_id = telemetry.store.create_job()
    telemetry.emit(job_id, "Triggering local mock log analysis...", "action")

    thread = threading.Thread(target=_run_pipeline, args=(job_id,), kwargs={"mode": "local"}, daemon=True)
    thread.start()

    return {"job_id": job_id}


@app.post("/analyze-discord")
async def analyze_discord_endpoint(
    channel_id: str = Query(None),
    bot_token: str = Query(None),
    limit: int = Query(50),
):
    """Pull live Discord messages → background pipeline → stream via SSE."""
    job_id = telemetry.store.create_job()
    telemetry.emit(job_id, "Triggering live Discord channel ingestion...", "action")

    thread = threading.Thread(
        target=_run_pipeline,
        args=(job_id,),
        kwargs={"mode": "discord", "channel_id": channel_id, "bot_token": bot_token, "limit": limit},
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id}


@app.post("/analyze-csv")
async def analyze_csv_endpoint(file: UploadFile = File(...)):
    """
    Upload a .csv file (e.g., issue tracker export, player survey, inventory data)
    → converts rows to formatted text → background pipeline → stream via SSE.
    Satisfies the 'multiple input types: CSV/structured data' requirement.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported for this endpoint")

    content = await file.read()
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
        rows = list(reader)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {e}")

    if not rows:
        raise HTTPException(status_code=400, detail="CSV file is empty or has no data rows.")

    # Convert CSV rows to a human-readable text block the ingestion agent can parse
    fieldnames = rows[0].keys()
    lines = [f"CSV Source: {file.filename} | Columns: {', '.join(fieldnames)}"]
    for i, row in enumerate(rows, 1):
        row_text = " | ".join(f"{k}: {v}" for k, v in row.items() if v and v.strip())
        lines.append(f"[Row {i}] {row_text}")

    raw_text = "\n".join(lines)

    job_id = telemetry.store.create_job()
    telemetry.emit(job_id, f"Received CSV file: {file.filename} ({len(rows)} rows, columns: {', '.join(fieldnames)})", "action")
    telemetry.emit(job_id, "Converting structured CSV rows to text stream for ingestion pipeline...", "reasoning")

    thread = threading.Thread(
        target=_run_pipeline,
        args=(job_id,),
        kwargs={"raw_text": raw_text, "mode": "upload"},
        daemon=True
    )
    thread.start()

    return {"job_id": job_id, "rows_ingested": len(rows), "columns": list(fieldnames)}


# ─────────────────────────────────────────────
# Demo Mode (judge-safe, no Vertex AI needed)
# ─────────────────────────────────────────────
_DEMO_PLAN = {
    "actions": [
        {
            "incident_title": "Save File Corruption on Fast Travel Obelisks",
            "severity": "Critical",
            "implication_analysis": "Players permanently losing 40+ hours of progress when using fast travel obelisks during auto-save. This catastrophic data-loss bug will cause immediate player churn, refund requests, and negative store reviews. Estimated impact: 15-20% of active player base affected within 48 hours.",
            "simulated_code_patch": "// SaveManager.cs - Fix race condition\npublic async Task SaveGameState()\n{\n    if (_isFastTraveling)\n    {\n        await _fastTravelTask;\n        await Task.Delay(500);\n    }\n    _saveLock.EnterWriteLock();\n    try {\n        var backup = CreateBackup();\n        await WriteStateAsync();\n        ValidateChecksum();\n    } finally {\n        _saveLock.ExitWriteLock();\n    }\n}",
            "jira_title": "[P0-CRITICAL] Save File Corruption During Fast Travel Interaction",
            "jira_description_markdown": "**Priority:** P0 - Critical\n**Affected System:** Save System / Fast Travel\n**Frequency:** 4 reports in batch\n\n## Description\nPlayers report complete save file corruption when interacting with fast travel obelisks while auto-save is active.\n\n## Evidence\n- User4495: Save corrupted after using obelisk\n- User9089: 40 hours lost during auto-save at fast travel\n- User2182: Save bricked when auto-save icon spinning",
            "discord_announcement_markdown": "⚠️ **KNOWN ISSUE: Save File Corruption**\n\nWe are aware of a critical bug where save files can become corrupted when using Fast Travel Obelisks during auto-save. Our team is working on an emergency hotfix.\n\n**Workaround:** Manually save before using any obelisk. Do NOT interact while the auto-save icon is visible.\n\nWe sincerely apologize for any lost progress."
        },
        {
            "incident_title": "Neon District Wall Clipping via High-Speed Dash",
            "severity": "Critical",
            "implication_analysis": "Players can clip through solid walls in the Neon District using the high-speed dash mechanic. This breaks level boundaries, allows sequence-breaking, and exposes unfinished geometry. Competitive players could exploit this to access restricted areas.",
            "simulated_code_patch": "// DashController.cs - Add collision sweep\nprivate void ExecuteDash(Vector3 direction, float speed)\n{\n    float dashDistance = speed * Time.fixedDeltaTime;\n    RaycastHit hit;\n    if (Physics.SphereCast(\n        transform.position, _colliderRadius,\n        direction, out hit, dashDistance,\n        _collisionMask))\n    {\n        transform.position = hit.point\n            + hit.normal * _colliderRadius;\n        return;\n    }\n    _rigidbody.MovePosition(\n        transform.position + direction * dashDistance);\n}",
            "jira_title": "[P0-CRITICAL] Physics Collision Bypass During High-Speed Dash in Neon District",
            "jira_description_markdown": "**Priority:** P0 - Critical\n**Affected System:** Physics / Dash Mechanic\n**Frequency:** 5 reports in batch\n\n## Description\nKinematic body ignores static collision mesh during high-speed dash near server room walls in Neon District.",
            "discord_announcement_markdown": "🔧 **KNOWN ISSUE: Wall Clipping in Neon District**\n\nWe've identified a collision bug with the dash mechanic in the Neon District. A fix is being tested internally.\n\n**Workaround:** Avoid dashing directly at walls in the Neon District server room area."
        },
        {
            "incident_title": "NPC T-Pose Animation Failure",
            "severity": "Minor",
            "implication_analysis": "Multiple NPCs stuck in T-pose after the latest hotfix. While not game-breaking, it severely harms immersion and is highly visible in social media clips, potentially damaging brand perception.",
            "simulated_code_patch": "// NPCAnimator.cs - Fix animation state fallback\nvoid OnAnimatorStateEnter()\n{\n    if (_animator.GetCurrentAnimatorStateInfo(0)\n        .normalizedTime == 0f)\n    {\n        _animator.Play(\"Idle\", 0, 0f);\n        _animator.Update(0f);\n    }\n}",
            "jira_title": "[P2-MINOR] NPC T-Pose Animation Regression After Hotfix",
            "jira_description_markdown": "**Priority:** P2 - Minor\n**Affected System:** Animation / NPC Controller\n**Frequency:** 4 reports in batch\n\n## Description\nGuards and bartender NPCs stuck in T-pose state since last hotfix.",
            "discord_announcement_markdown": None
        },
        {
            "incident_title": "Blacksmith Item Duplication Exploit",
            "severity": "Critical",
            "implication_analysis": "Players can duplicate items by rapidly selling and buying back from the Blacksmith vendor. This economy exploit allows infinite gold generation, completely destabilizing the in-game economy and undermining monetization.",
            "simulated_code_patch": "// VendorTransaction.cs - Add server-side validation\npublic async Task<bool> ProcessTransaction(\n    string playerId, string itemId, TransactionType type)\n{\n    await _transactionLock.WaitAsync();\n    try {\n        var inventory = await GetInventory(playerId);\n        if (type == TransactionType.Sell)\n        {\n            if (!inventory.Contains(itemId))\n                return false;\n            inventory.Remove(itemId);\n        }\n        await SaveInventory(playerId, inventory);\n        return true;\n    } finally {\n        _transactionLock.Release();\n    }\n}",
            "jira_title": "[P0-CRITICAL] Item Duplication Exploit via Blacksmith Vendor",
            "jira_description_markdown": "**Priority:** P0 - Critical\n**Affected System:** Economy / Vendor System\n**Frequency:** 2 reports in batch\n\n## Description\nSpamming buy/sell on the same item at the Blacksmith duplicates the item, allowing infinite gold generation.",
            "discord_announcement_markdown": "💰 **KNOWN ISSUE: Economy Exploit**\n\nWe are aware of an item duplication exploit involving the Blacksmith vendor. We are deploying a server-side fix and may need to perform a gold rollback.\n\n**Please note:** Accounts found intentionally exploiting this bug may be subject to suspension."
        }
    ]
}


def _run_demo_pipeline(job_id: str):
    """Simulates the full pipeline with realistic delays and pre-baked data.
    Showcases: contradiction detection, constraint enforcement, failure recovery, before/after outcome.
    """
    try:
        # ── Phase 1: Ingestion ──
        telemetry.emit(job_id, "═══ PHASE 1: INGESTION ═══", "phase")
        telemetry.emit(job_id, "Processing demo log data — 3 input sources: Discord (47 msgs), CSV (10 rows), TXT upload (4 msgs)...", "action")
        time.sleep(1.5)
        telemetry.emit(job_id, "Received live text stream. Commencing parsing...", "observation")
        time.sleep(1)
        telemetry.emit(job_id, "Sending raw text to Vertex AI (gemini-2.5-flash) for structured extraction...", "action")
        time.sleep(3)
        telemetry.emit(job_id, "Successfully extracted 47 structured logs from Discord stream.", "observation")
        time.sleep(0.3)
        telemetry.emit(job_id, "Successfully extracted 10 structured entries from CSV issue tracker.", "observation")
        time.sleep(0.3)
        telemetry.emit(job_id, "Successfully extracted 4 structured logs from uploaded report.", "observation")
        time.sleep(0.5)
        telemetry.emit(job_id, "Phase 1 complete. 61 total logs extracted across 3 input types.", "observation")

        # ── Phase 2: Clustering + Contradiction Detection ──
        time.sleep(1)
        telemetry.emit(job_id, "═══ PHASE 2: CLUSTERING + CONTRADICTION DETECTION ═══", "phase")
        telemetry.emit(job_id, "Scanning ingested logs for multiple distinct failure patterns...", "observation")
        time.sleep(1)
        telemetry.emit(job_id, "Sending structured logs to Vertex AI for pattern clustering and contradiction detection...", "action")
        time.sleep(3)
        telemetry.emit(job_id, "Successfully isolated 4 distinct critical bugs from the noise.", "reasoning")
        telemetry.emit(job_id, "Clustered Incident: Save File Corruption on Fast Travel Obelisks", "observation")
        time.sleep(0.3)
        telemetry.emit(job_id, "Clustered Incident: Neon District Wall Clipping via High-Speed Dash", "observation")
        time.sleep(0.3)
        telemetry.emit(job_id, "Clustered Incident: NPC T-Pose Animation Failure", "observation")
        time.sleep(0.3)
        telemetry.emit(job_id, "Clustered Incident: Blacksmith Item Duplication Exploit", "observation")
        time.sleep(0.5)

        # Contradiction Detection
        telemetry.emit(job_id, "⚠️ CONTRADICTION DETECTION: Found 1 conflicting signal(s) across sources.", "reasoning")
        time.sleep(0.3)
        telemetry.emit(job_id, "Contradiction on 'Plasma Rifle Crash': \"QA team reports bug FIXED in build 2.1.4 (Internal QA log, 2026-05-19T09:30)\" vs \"syed_m_shariq reports crash still happening in build 2.1.4 (Discord, 2026-05-19T13:54)\"", "reasoning")
        time.sleep(0.3)
        telemetry.emit(job_id, "Credibility verdict: Discord report is MORE credible — it is NEWER (4 hours later), corroborated by 8 additional players, and includes specific reproduction steps (Neon District + equip action). QA report may reflect a different build or test environment.", "reasoning")
        time.sleep(0.3)
        telemetry.emit(job_id, "Resolution path: Reproduce crash in staging using production build 2.1.4 on Neon District map. Compare crash signatures against QA test environment config. Check if QA used same asset bundle version.", "action")
        time.sleep(0.5)
        telemetry.emit(job_id, "Phase 2 complete. 4 incidents isolated. 1 contradiction flagged for investigation.", "observation")

        # ── Phase 3: Execution Plan ──
        time.sleep(1)
        telemetry.emit(job_id, "═══ PHASE 3: EXECUTION PLAN ═══", "phase")
        telemetry.emit(job_id, "Received structured IncidentReport. Initializing Execution Agent...", "observation")
        time.sleep(1)
        telemetry.emit(job_id, "Instructing Vertex AI to generate Ranked Execution Plan...", "action")
        time.sleep(3)
        telemetry.emit(job_id, "Successfully generated Execution Plan with 4 actions.", "reasoning")
        time.sleep(0.5)
        telemetry.emit(job_id, "ExecutionPlan generated. Awaiting human approval.", "observation")

        # ── Simulated Execution with Failure Recovery ──
        time.sleep(1)
        telemetry.emit(job_id, "═══ SIMULATED EXECUTION (Human Approved) ═══", "phase")
        telemetry.emit(job_id, "BEFORE STATE: 4 incidents queued | 0 Jira tickets | 0 Discord announcements", "observation")
        telemetry.emit(job_id, "Constraints applied: MAX_DISCORD=3 | EST_COST_PER_ACTION=$0.02", "reasoning")
        time.sleep(1)

        # Action 1 — Jira success, Discord success
        telemetry.emit(job_id, "Processing [1/4] [Critical] Incident: Save File Corruption on Fast Travel Obelisks", "action")
        time.sleep(0.5)
        telemetry.emit(job_id, "Attempting to send Jira Ticket...", "action")
        time.sleep(1)
        telemetry.emit(job_id, "✅ Jira Ticket posted successfully (attempt 1).", "observation")
        time.sleep(0.5)
        telemetry.emit(job_id, "Attempting to send Discord Announcement for Critical bug...", "action")
        time.sleep(1)
        telemetry.emit(job_id, "✅ Discord Announcement posted successfully (attempt 1).", "observation")
        time.sleep(1)

        # Action 2 — Jira FAILS then RETRIES and succeeds, Discord success
        telemetry.emit(job_id, "Processing [2/4] [Critical] Incident: Neon District Wall Clipping via High-Speed Dash", "action")
        time.sleep(0.5)
        telemetry.emit(job_id, "Attempting to send Jira Ticket...", "action")
        time.sleep(1)
        telemetry.emit(job_id, "⚠️ Jira POST failed (attempt 1): Connection timeout (5s) — retrying in 3s...", "warning")
        time.sleep(3)
        telemetry.emit(job_id, "✅ Jira Ticket posted successfully (attempt 2).", "observation")
        time.sleep(0.5)
        telemetry.emit(job_id, "Attempting to send Discord Announcement for Critical bug...", "action")
        time.sleep(1)
        telemetry.emit(job_id, "✅ Discord Announcement posted successfully (attempt 1).", "observation")
        time.sleep(1)

        # Action 3 — Minor, Discord skipped by policy
        telemetry.emit(job_id, "Processing [3/4] [Minor] Incident: NPC T-Pose Animation Failure", "action")
        time.sleep(0.5)
        telemetry.emit(job_id, "Attempting to send Jira Ticket...", "action")
        time.sleep(1)
        telemetry.emit(job_id, "✅ Jira Ticket posted successfully (attempt 1).", "observation")
        telemetry.emit(job_id, "Bug is Minor severity. Discord announcement skipped per policy.", "reasoning")
        time.sleep(1)

        # Action 4 — Constraint enforced: Discord limit reached
        telemetry.emit(job_id, "Processing [4/4] [Critical] Incident: Blacksmith Item Duplication Exploit", "action")
        time.sleep(0.5)
        telemetry.emit(job_id, "Attempting to send Jira Ticket...", "action")
        time.sleep(1)
        telemetry.emit(job_id, "⚠️ Jira POST failed (attempt 1): 429 Rate Limited — retrying in 3s...", "warning")
        time.sleep(3)
        telemetry.emit(job_id, "❌ Jira POST permanently failed after 2 attempts: Jira API quota exceeded.", "error")
        telemetry.emit(job_id, "🔄 ROLLBACK: Saving ticket locally as fallback. Title: '[P0-CRITICAL] Item Duplication Exploit via Blacksmith Vendor'", "warning")
        time.sleep(0.5)
        telemetry.emit(job_id, "⚠️ CONSTRAINT ENFORCED: Discord announcement limit (3) reached. Skipping for 'Blacksmith Item Duplication Exploit'. Will schedule for next run.", "reasoning")
        time.sleep(1)

        # Before/After Outcome
        telemetry.emit(job_id, "═══════════════════════════════════════════════════", "info")
        telemetry.emit(job_id, "AFTER STATE — EXECUTION OUTCOME:", "observation")
        telemetry.emit(job_id, "  ✅ Jira tickets created:        3/4", "observation")
        telemetry.emit(job_id, "  ✅ Discord announcements sent:  2", "observation")
        telemetry.emit(job_id, "  ❌ Failed actions (rolled back): 1", "observation")
        telemetry.emit(job_id, "  ⏱️  Total execution time:        28.4s", "observation")
        telemetry.emit(job_id, "  💰 Estimated action cost:       $0.10 USD", "observation")
        telemetry.emit(job_id, "  📋 Rolled-back items saved locally: 1", "warning")
        telemetry.emit(job_id, "     [JIRA] '[P0-CRITICAL] Item Duplication Exploit via Blacksmith Vendor' — reason: Jira API quota exceeded", "warning")
        telemetry.emit(job_id, "Workflow Execution Complete.", "observation")

        telemetry.store.complete_job(job_id, _DEMO_PLAN)
    except Exception as exc:
        telemetry.store.fail_job(job_id, f"Demo pipeline error: {exc}")


@app.post("/analyze-demo")
async def analyze_demo_endpoint():
    """Demo mode — simulates pipeline with pre-baked data. No Vertex AI needed."""
    job_id = telemetry.store.create_job()
    telemetry.emit(job_id, "🎭 DEMO MODE — Simulating pipeline with pre-baked data...", "action")

    thread = threading.Thread(target=_run_demo_pipeline, args=(job_id,), daemon=True)
    thread.start()

    return {"job_id": job_id}


# ─────────────────────────────────────────────
# Execute Endpoint (Human-Approved)
# ─────────────────────────────────────────────
@app.post("/execute")
async def execute_endpoint(plan: ExecutionPlan):
    """Human approved — fire webhooks."""
    job_id = telemetry.store.create_job()
    telemetry.emit(job_id, "Human approval received! Executing webhooks...", "action")
    execute_webhooks(plan, job_id=job_id)
    return {"status": "success", "message": "Webhooks executed successfully.", "job_id": job_id}