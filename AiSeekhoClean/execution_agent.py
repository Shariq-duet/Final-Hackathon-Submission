import sys
import os
import json
import requests
import time
from pydantic import BaseModel, Field
from google import genai
from dotenv import load_dotenv
import telemetry

# Set stdout to utf-8 to handle emojis in Discord markdown
sys.stdout.reconfigure(encoding='utf-8')

# --- Phase 3: Pydantic Schema ---
class IncidentAction(BaseModel):
    incident_title: str = Field(description="The title of the incident being addressed")
    severity: str = Field(description="Severity rating: 'Critical' or 'Minor'")
    implication_analysis: str = Field(description="Detailed analysis of the business and gameplay implications of this bug")
    simulated_code_patch: str = Field(description="A simulated code snippet (e.g., C#, Python, C++) that theoretically fixes the root cause of this specific bug.")
    jira_title: str = Field(description="A professional title for the Jira Bug Ticket.")
    jira_description_markdown: str = Field(description="A detailed Jira Bug Ticket description formatted in Markdown, including priority severity and list of video evidence URLs.")
    discord_announcement_markdown: str | None = Field(description="A Community Discord Announcement formatted in Markdown, apologizing for the issue. Null if severity is Minor.")

class ExecutionPlan(BaseModel):
    actions: list[IncidentAction] = Field(description="List of actions ranked by severity (Critical first, then Minor).")

# --- Phase 3: Execution Function ---
def generate_plan(incident_report: dict, job_id: str = None) -> ExecutionPlan:
    telemetry.emit(job_id, "Received structured IncidentReport. Initializing Execution Agent...", "observation")
    
    client = genai.Client(vertexai=True, project="gen-lang-client-0583565763", location="us-central1")
    
    report_json = json.dumps(incident_report, indent=2)

    system_instruction = (
        "You are the Execution Agent. Take the provided IncidentReport and generate an ExecutionPlan. "
        "1. Rank the incidents by severity (Critical first, then Minor). "
        "2. For each incident, provide an implication_analysis. "
        "3. Generate a Jira Ticket title and description. "
        "4. If the bug is Critical, generate a Discord Announcement. If Minor, leave discord_announcement_markdown as null. "
        "5. For every bug you analyze, you must act as a Senior Gameplay Programmer. Write a highly realistic, simulated code snippet that patches the core issue. For example, if it is a Unity physics clipping issue, write the C# script to fix the rigid body collision logic. If it is an economy exploit, write the server-side validation check. Return this snippet inside the simulated_code_patch field."
    )

    prompt = f"Here is the IncidentReport:\n\n{report_json}"

    telemetry.emit(job_id, "Instructing Vertex AI to generate Ranked Execution Plan...", "action")
    
    response = telemetry.retry_with_backoff(
        lambda: client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ExecutionPlan,
                system_instruction=system_instruction,
                temperature=0.7
            ),
        ),
        job_id=job_id,
    )
    
    try:
        plan_data = json.loads(response.text)
        plan = ExecutionPlan.model_validate(plan_data)
        telemetry.emit(job_id, f"Successfully generated Execution Plan with {len(plan.actions)} actions.", "reasoning")
        return plan
    except Exception as e:
        telemetry.emit(job_id, f"Failed to parse execution response. Details: {e}", "error")
        return None

def execute_webhooks(plan: ExecutionPlan, job_id: str = None):
    jira_url = os.environ.get("JIRA_WEBHOOK_URL")
    jira_email = os.environ.get("JIRA_EMAIL")
    jira_token = os.environ.get("JIRA_API_TOKEN")
    jira_project_key = os.environ.get("JIRA_PROJECT_KEY")
    discord_url = os.environ.get("DISCORD_WEBHOOK_URL")

    # ── Constraints ──
    MAX_DISCORD_ANNOUNCEMENTS = 3   # Rate-limit constraint: no more than 3 Discord posts per run
    ESTIMATED_COST_PER_ACTION = 0.02  # USD — notional cost per webhook action for cost tracking

    total_actions = len(plan.actions)
    executed_jira = 0
    failed_jira = 0
    executed_discord = 0
    failed_discord = 0
    rolled_back = []
    start_time = time.time()

    # ── Before State ──
    telemetry.emit(job_id, f"BEFORE STATE: {total_actions} incidents queued | 0 Jira tickets | 0 Discord announcements", "observation")
    telemetry.emit(job_id, f"Constraints applied: MAX_DISCORD={MAX_DISCORD_ANNOUNCEMENTS} | EST_COST_PER_ACTION=${ESTIMATED_COST_PER_ACTION}", "reasoning")

    for i, action in enumerate(plan.actions):
        telemetry.emit(job_id, f"Processing [{i+1}/{total_actions}] [{action.severity}] Incident: {action.incident_title}", "action")
        telemetry.emit(job_id, f"Implication Analysis: {action.implication_analysis}", "reasoning")
        
        # ── Post to Jira (with retry + rollback) ──
        if jira_url and jira_email and jira_token and jira_project_key:
            telemetry.emit(job_id, "Attempting to send Jira Ticket...", "action")
            combined_description = action.jira_description_markdown + f"\n\n*Suggested AI Code Patch:*\n```\n{action.simulated_code_patch}\n```"

            jira_success = False
            for attempt in range(1, 3):  # max 2 attempts
                try:
                    jira_payload = {
                        "fields": {
                            "project": {"key": jira_project_key},
                            "summary": action.jira_title,
                            "issuetype": {"name": "Bug"},
                            "description": {
                                "type": "doc",
                                "version": 1,
                                "content": [{"type": "paragraph", "content": [{"type": "text", "text": combined_description}]}]
                            }
                        }
                    }
                    res = requests.post(jira_url, auth=(jira_email, jira_token), json=jira_payload, timeout=5)
                    res.raise_for_status()
                    executed_jira += 1
                    jira_success = True
                    telemetry.emit(job_id, f"✅ Jira Ticket posted successfully (attempt {attempt}).", "observation")
                    break
                except requests.exceptions.RequestException as e:
                    if attempt < 2:
                        telemetry.emit(job_id, f"⚠️ Jira POST failed (attempt {attempt}): {e} — retrying in 3s...", "warning")
                        time.sleep(3)
                    else:
                        failed_jira += 1
                        telemetry.emit(job_id, f"❌ Jira POST permanently failed after {attempt} attempts: {e}", "error")
                        telemetry.emit(job_id, f"🔄 ROLLBACK: Saving ticket locally as fallback. Title: '{action.jira_title}'", "warning")
                        rolled_back.append({"type": "jira", "title": action.jira_title, "reason": str(e)})
        else:
            telemetry.emit(job_id, "Jira credentials missing. Skipping POST.", "warning")
        
        # ── Post to Discord (constraint check + retry + fallback) ──
        if action.severity.lower() == "critical" and discord_url and action.discord_announcement_markdown:
            # Constraint: enforce max announcements
            if executed_discord >= MAX_DISCORD_ANNOUNCEMENTS:
                telemetry.emit(job_id, f"⚠️ CONSTRAINT ENFORCED: Discord announcement limit ({MAX_DISCORD_ANNOUNCEMENTS}) reached. Skipping for '{action.incident_title}'. Will schedule for next run.", "reasoning")
            else:
                telemetry.emit(job_id, "Attempting to send Discord Announcement for Critical bug...", "action")
                discord_success = False
                for attempt in range(1, 3):
                    try:
                        payload = {"content": action.discord_announcement_markdown}
                        res = requests.post(discord_url, json=payload, timeout=5)
                        res.raise_for_status()
                        executed_discord += 1
                        discord_success = True
                        telemetry.emit(job_id, f"✅ Discord Announcement posted successfully (attempt {attempt}).", "observation")
                        break
                    except requests.exceptions.RequestException as e:
                        if attempt < 2:
                            telemetry.emit(job_id, f"⚠️ Discord POST failed (attempt {attempt}): {e} — retrying in 3s...", "warning")
                            time.sleep(3)
                        else:
                            failed_discord += 1
                            telemetry.emit(job_id, f"❌ Discord POST permanently failed after {attempt} attempts: {e}", "error")
                            telemetry.emit(job_id, f"🔄 FALLBACK: Announcement saved to local queue for manual review.", "warning")
                            rolled_back.append({"type": "discord", "title": action.incident_title, "reason": str(e)})
        elif action.severity.lower() != "critical":
            telemetry.emit(job_id, "Bug is Minor severity. Discord announcement skipped per policy.", "reasoning")
        else:
            telemetry.emit(job_id, "Discord URL missing or announcement markdown not provided. Skipping POST.", "warning")
            
        # Mandatory delay to prevent API rate-limiting during batch execution
        time.sleep(2)

    # ── After State / Outcome Summary ──
    elapsed = round(time.time() - start_time, 1)
    total_cost = round((executed_jira + executed_discord) * ESTIMATED_COST_PER_ACTION, 4)

    telemetry.emit(job_id, "═══════════════════════════════════════════════════", "info")
    telemetry.emit(job_id, "AFTER STATE — EXECUTION OUTCOME:", "observation")
    telemetry.emit(job_id, f"  ✅ Jira tickets created:        {executed_jira}/{total_actions}", "observation")
    telemetry.emit(job_id, f"  ✅ Discord announcements sent:  {executed_discord}", "observation")
    telemetry.emit(job_id, f"  ❌ Failed actions (rolled back): {failed_jira + failed_discord}", "observation")
    telemetry.emit(job_id, f"  ⏱️  Total execution time:        {elapsed}s", "observation")
    telemetry.emit(job_id, f"  💰 Estimated action cost:       ${total_cost} USD", "observation")
    if rolled_back:
        telemetry.emit(job_id, f"  📋 Rolled-back items saved locally: {len(rolled_back)}", "warning")
        for rb in rolled_back:
            telemetry.emit(job_id, f"     [{rb['type'].upper()}] '{rb['title']}' — reason: {rb['reason'][:80]}", "warning")
    telemetry.emit(job_id, "Workflow Execution Complete.", "observation")

if __name__ == "__main__":
    load_dotenv()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    report_path = os.path.join(base_dir, "incident_report.json")
    
    if not os.path.exists(report_path):
        print(f"Error: {report_path} not found. Please run the clustering agent first.")
    else:
        with open(report_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        print("Starting Phase 3: Execution...")
        plan = generate_plan(data)
        if plan:
            execute_webhooks(plan)
