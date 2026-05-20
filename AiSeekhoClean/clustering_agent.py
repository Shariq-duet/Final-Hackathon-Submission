import os
import json
from pydantic import BaseModel, Field
from google import genai
from dotenv import load_dotenv
import telemetry

# Re-define LogEntry just for typing context
class LogEntry(BaseModel):
    log_id: str
    timestamp: str
    platform: str
    username: str
    category_tag: str
    message_text: str
    media_url: str | None = None

# --- Phase 2: Pydantic Schema ---
class IncidentReport(BaseModel):
    incident_title: str = Field(description="High-level title of the incident")
    affected_system: str = Field(description="The specific system, level, or mechanic affected")
    aggregated_description: str = Field(description="Synthesized description of the recurring symptoms")
    report_frequency: int = Field(description="Exact count of the specific bug occurrences in the provided batch")
    evidence_urls: list[str] = Field(description="List of all media URLs associated with the clustered bug reports")

class ContradictionReport(BaseModel):
    topic: str = Field(description="The bug or system where contradicting claims exist")
    claim_a: str = Field(description="First conflicting claim, including which user/source made it")
    claim_b: str = Field(description="Second conflicting claim, including which user/source made it")
    credibility_verdict: str = Field(description="Which claim is more credible and why (consider recency, specificity, number of corroborating reports)")
    resolution_path: str = Field(description="Recommended investigation action to resolve the contradiction, e.g. 'Check server logs for timestamp X' or 'Reproduce in staging with patch Y'")

class ClusteredInsights(BaseModel):
    incidents: list[IncidentReport]
    contradictions: list[ContradictionReport] = Field(
        default=[],
        description="List of detected contradictions where sources make conflicting claims about the same bug or system"
    )

# --- Phase 2: Clustering Function ---
# CRITICAL FIX: Renamed to run_clustering and accepts a list of dicts from server.py
def run_clustering(ingested_data: list[dict], job_id: str = None) -> dict:
    telemetry.emit(job_id, "Scanning ingested logs for multiple distinct failure patterns...", "observation")
    
    load_dotenv()
    client = genai.Client(vertexai=True, project="gen-lang-client-0583565763", location="us-central1")
    
    logs_json = json.dumps(ingested_data, indent=2)

    system_instruction = (
        "You are a game bug triage analyst. You will receive a JSON array of community Discord messages.\n\n"
        "Your job has TWO parts:\n\n"
        "PART 1 - BUG CLUSTERING:\n"
        "Identify ALL distinct software bugs reported. A bug is any technical malfunction, crash, "
        "exploit, broken mechanic, incorrect behavior, or game-breaking issue reported by players.\n\n"
        "INCLUDE: crashes, corrupted saves, broken AI, physics issues, clipping, animation locks, hitbox problems, "
        "quest marker errors, loot bugs, FPS drops, audio issues, economy exploits, UI setting resets.\n\n"
        "EXCLUDE ONLY: pure opinions ('game is bad'), social messages ('LFG', 'GG'), and lore discussions.\n\n"
        "When in doubt, INCLUDE the bug. It is better to over-report than miss a critical issue.\n\n"
        "For each distinct bug type found, synthesize all related messages into ONE IncidentReport.\n"
        "Set report_frequency to the number of messages that describe that specific bug.\n"
        "If no media_url exists in the related messages, set evidence_urls to an empty list [].\n\n"
        "Return ALL discovered incidents in the incidents array. Do not return an empty array unless "
        "there are genuinely zero bug reports in the input.\n\n"
        "PART 2 - CONTRADICTION DETECTION:\n"
        "After clustering, analyze the messages for CONTRADICTIONS — cases where two or more users make "
        "conflicting factual claims about the SAME bug or system. Examples of contradictions:\n"
        "- One user says 'plasma rifle works fine for me', another says 'plasma rifle crashes every time'\n"
        "- One user says 'save corruption is fixed', another says 'still happening after patch'\n"
        "- One source reports stock is sufficient, another reports imminent shortage\n\n"
        "For each contradiction found:\n"
        "1. Identify the two conflicting claims and who made them\n"
        "2. Score which claim is more credible based on: recency (newer timestamp wins), "
        "specificity (detailed reproduction steps beat vague reports), and corroboration (claim supported "
        "by more users wins)\n"
        "3. Propose a concrete resolution path — what investigation step would resolve the conflict?\n\n"
        "Return contradictions in the contradictions array. If no contradictions exist, return an empty list []."
    )

    prompt = f"Here is the parsed JSON array of community logs for your analysis:\n\n{logs_json}"
    
    telemetry.emit(job_id, "Sending structured logs to Vertex AI for pattern clustering and contradiction detection...", "action")
    
    response = telemetry.retry_with_backoff(
        lambda: client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ClusteredInsights,
                system_instruction=system_instruction,
                temperature=0.0
            ),
        ),
        job_id=job_id,
    )
    
    try:
        insights_data = json.loads(response.text)
        insights = ClusteredInsights.model_validate(insights_data)
        
        telemetry.emit(job_id, f"Successfully isolated {len(insights.incidents)} distinct critical bugs from the noise.", "reasoning")
        for incident in insights.incidents:
            telemetry.emit(job_id, f"Clustered Incident: {incident.incident_title}", "observation")
            
        # --- Contradiction reporting ---
        if insights.contradictions:
            telemetry.emit(job_id, f"⚠️ CONTRADICTION DETECTION: Found {len(insights.contradictions)} conflicting signal(s) across sources.", "reasoning")
            for contradiction in insights.contradictions:
                telemetry.emit(job_id, f"Contradiction on '{contradiction.topic}': \"{contradiction.claim_a}\" vs \"{contradiction.claim_b}\"", "reasoning")
                telemetry.emit(job_id, f"Credibility verdict: {contradiction.credibility_verdict}", "reasoning")
                telemetry.emit(job_id, f"Resolution path: {contradiction.resolution_path}", "action")
        else:
            telemetry.emit(job_id, "No contradictions detected across sources. All reports are consistent.", "observation")
            
        return insights.model_dump()
    except Exception as e:
        telemetry.emit(job_id, f"Failed to parse clustering response. Details: {e}", "error")
        telemetry.emit(job_id, f"Raw response text: {response.text[:500]}", "error")
        return ClusteredInsights(incidents=[], contradictions=[]).model_dump()

# We omit the __main__ block here because Google Cloud Run does not use it. 
# The server.py file handles all execution now.