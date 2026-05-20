import os
import json
import requests
from dotenv import load_dotenv

# Load env variables using absolute path
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")  # Set in .env file
CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "1506288745748365558")
LIMIT = 50

# ── Step 1: Pull raw messages from Discord ──
print("=" * 60)
print("STEP 1: Fetching raw Discord messages...")
print("=" * 60)

headers = {"Authorization": f"Bot {BOT_TOKEN}"}
url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit={LIMIT}"

response = requests.get(url, headers=headers)
messages = response.json()

print(f"Fetched {len(messages)} messages\n")
for i, msg in enumerate(messages):
    author = msg.get("author", {}).get("username", "unknown")
    content = msg.get("content", "")
    attachments = msg.get("attachments", [])
    print(f"[{i+1}] {author}: {content[:100]}")
    if attachments:
        print(f"     📎 Has attachment: {attachments[0].get('url', '')[:60]}")

# ── Step 2: Format exactly as ingestion_agent does ──
print("\n" + "=" * 60)
print("STEP 2: Formatted log strings (what Phase 1 sends to Gemini)...")
print("=" * 60)

log_strings = []
for msg in messages:
    content = msg.get("content", "").strip()
    if not content:
        continue
    author = msg.get("author", {}).get("username", "unknown")
    timestamp = msg.get("timestamp", "")
    attachments = msg.get("attachments", [])
    media_url = attachments[0].get("url") if attachments else None

    log_line = f"[{timestamp}] {author}: {content}"
    if media_url:
        log_line += f" [media: {media_url}]"
    log_strings.append(log_line)

formatted_text = "\n".join(log_strings)
print(formatted_text)

# ── Step 3: Send to Gemini and print raw response ──
print("\n" + "=" * 60)
print("STEP 3: Sending to Gemini — raw extraction response...")
print("=" * 60)

from google import genai
from google.genai import types

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not set in environment variables or .env file")
print(f"DEBUG: GEMINI_API_KEY found in env: {api_key is not None}")
client = genai.Client(api_key=api_key)

extraction_prompt = f"""
You are analyzing Discord messages from a game community.
Identify and extract any bug reports. For each bug found, output:
- username
- what bug they are reporting
- severity guess (Critical/Major/Minor)
- any media attached

Here are the messages:

{formatted_text}

Respond in JSON format as a list of objects with fields: username, bug_description, severity, media_url
"""

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=extraction_prompt,
)

print("RAW GEMINI RESPONSE:")
print(response.text)

# ── Step 4: Try to parse and summarize ──
print("\n" + "=" * 60)
print("STEP 4: Summary")
print("=" * 60)

try:
    clean = response.text.strip().replace("```json", "").replace("```", "").strip()
    parsed = json.loads(clean)
    print(f"Gemini found {len(parsed)} bug reports in your Discord channel:\n")
    for bug in parsed:
        print(f"  • [{bug.get('severity', '?')}] {bug.get('username')}: {bug.get('bug_description', '')[:80]}")
except Exception as e:
    print(f"Could not parse response as JSON: {e}")
    print("Check the raw response above to see what Gemini actually returned.")