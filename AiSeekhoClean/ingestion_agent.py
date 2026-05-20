import os
import json
import time
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
import telemetry

class LogEntry(BaseModel):
    log_id: str = Field(description="Unique ID in format MSG-XXXX, starting sequentially from MSG-8842")
    timestamp: str = Field(description="Timestamp of the message in format YYYY-MM-DDTHH:MM:SSZ. Infer from log or use a default if missing.")
    platform: str = Field(description="Platform the message was sent on, e.g. Discord, Reddit")
    username: str = Field(description="Username of the sender")
    category_tag: str = Field(description="Category tag: Bug_Report (for critical collision/physics issues) or General (for UI/Lore/Lag complaints)")
    message_text: str = Field(description="The actual message content")
    media_url: str | None = Field(description="URL of the media if present, else null", default=None)

class IngestedLogs(BaseModel):
    logs: list[LogEntry]


# --- Discord Live Fetch ---
def fetch_discord_messages(channel_id: str = None, bot_token: str = None, limit: int = 50, job_id: str = None) -> list[str]:
    load_dotenv()

    channel_id = channel_id or os.getenv("DISCORD_CHANNEL_ID")
    bot_token = bot_token or os.getenv("DISCORD_BOT_TOKEN")

    if not channel_id or not bot_token:
        raise ValueError(
            "Missing DISCORD_CHANNEL_ID or DISCORD_BOT_TOKEN. "
            "Set them as environment variables or pass them as arguments."
        )

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}"
    headers = {"Authorization": f"Bot {bot_token}"}

    telemetry.emit(job_id, f"Fetching up to {limit} messages from Discord channel {channel_id}...", "action")
    response = requests.get(url, headers=headers, timeout=15)

    if response.status_code != 200:
        raise ConnectionError(
            f"Discord API returned {response.status_code}: {response.text}"
        )

    messages = response.json()
    telemetry.emit(job_id, f"Received {len(messages)} messages from Discord API.", "observation")

    formatted_logs = []
    for msg in messages:
        content = msg.get("content", "").strip()
        if not content:
            continue  # skip empty/non-text messages

        author = msg.get("author", {}).get("username", "unknown_user")
        timestamp = msg.get("timestamp", "")

        # ── preserve ALL attachments alongside the message ──
        attachment_urls = [a.get("url", "") for a in msg.get("attachments", []) if a.get("url")]
        
        line = f"[{timestamp}] [{author}] (platform: Discord): {content}"
        if attachment_urls:
            line += f" [media: {', '.join(attachment_urls)}]"

        formatted_logs.append(line)

    telemetry.emit(job_id, f"Formatted {len(formatted_logs)} non-empty messages into log strings.", "observation")
    return formatted_logs

# --- Vertex AI Ingestion (unchanged core logic) ---
def run_ingestion(raw_text: str, job_id: str = None) -> list[dict]:
    telemetry.emit(job_id, "Received live text stream. Commencing parsing...", "observation")
    load_dotenv()
    
    # Deferred initialization to prevent boot-crashes
    client = genai.Client(vertexai=True, project="gen-lang-client-0583565763", location="us-central1")
    
    system_instruction = """
    You are the primary Ingestion Agent for our Challenge 1 workflow.
    Your strict mandate is to parse unstructured natural language and transform it into a highly structured JSON array.
    Extract the relevant player complaints along with any associated media URLs.
    If a message does not contain a media URL, you must set the media_url to null.
    Infer the platform from the text if possible, or default to Discord.

    CATEGORIZATION RULES:
    - Use 'Bug_Report' for ANY technical issue: crashes, corrupted saves, broken mechanics, 
    physics bugs, AI issues, clipping, animation problems, hitbox errors, economy exploits,
    FPS drops, audio issues, missing content, or any unintended game behavior.
    - Use 'General' ONLY for: pure social messages (LFG, GG), lore discussions, or 
    messages with zero technical content.
    - When in doubt, use 'Bug_Report'. It is better to over-tag than miss a real bug.

    Map the extracted information perfectly to the schema.
    """

    prompt = f"Parse the following unstructured logs into the requested JSON schema:\n\n{raw_text}"
    
    telemetry.emit(job_id, "Sending raw text to Vertex AI (gemini-2.5-flash) for structured extraction...", "action")
    
    try:
        response = telemetry.retry_with_backoff(
            lambda: client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=IngestedLogs,
                    system_instruction=system_instruction,
                    temperature=0.0
                ),
            ),
            job_id=job_id,
        )
        
        response_data = json.loads(response.text)
        logs = response_data.get("logs", [])
        telemetry.emit(job_id, f"Successfully extracted {len(logs)} structured logs from the stream.", "observation")
        return logs
        
    except Exception as e:
        telemetry.emit(job_id, f"Failed to parse logs. Details: {e}", "error")
        return []


# --- Convenience: Fetch + Parse in one call ---
def run_discord_ingestion(channel_id: str = None, bot_token: str = None, limit: int = 50, job_id: str = None) -> list[dict]:
    """
    End-to-end: fetches live Discord messages, then feeds them
    through the existing Vertex AI ingestion pipeline.
    """
    log_strings = fetch_discord_messages(channel_id, bot_token, limit, job_id=job_id)

    if not log_strings:
        telemetry.emit(job_id, "No messages retrieved from Discord. Aborting ingestion.", "warning")
        return []

    raw_text = "\n".join(log_strings)
    return run_ingestion(raw_text, job_id=job_id)


if __name__ == "__main__":
    results = run_discord_ingestion()
    print(json.dumps(results, indent=2))