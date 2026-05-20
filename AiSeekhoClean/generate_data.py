import requests
import time
import os
from dotenv import load_dotenv

# Load env variables from .env file
load_dotenv()

# Webhook URL from env with fallback
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL_BUG", os.getenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1506618474498359317/ImD_RYRW6qhidm-litxitc1KTc-npjKlLlkuvVr7pS0K4sZ9J7l5mv0s4TllkCcp4IB3"))

# Path to images folder
IMAGES_FOLDER = r"C:\Users\PMLS\Downloads\AiSeekhoClean\images"

# The expanded mock dataset mapped to correct image filenames
mock_data = [
    {"user": "NeonNinja",      "msg": "Major issue in the new patch. Every time I equip the plasma rifle, the game hard crashes.", "image": None},
    {"user": "RaidHealer99",   "msg": "Are fast travel obelisks safe? My save file corrupted yesterday after using one.", "image": "savefilecorruption.png"},
    {"user": "MetaGamer",      "msg": "The actual problem is that plasma ammo costs 50k gold now. Economy is completely ruined.", "image": None},
    {"user": "PlasmaMain",     "msg": "DO NOT EQUIP PLASMA RIFLE. Bricked my entire session against the Cyber-Dragon boss.", "image": None},
    {"user": "TrollAccount",   "msg": "LF2M for the raid, need a healer and a tank. Also plasma rifle goes brrrr.", "image": None},
    {"user": "AngryNoob",      "msg": "Game is literally unplayable. Plasma rifle crashed me 5 times in a row!", "image": "plasmarifecrash.png"},
    {"user": "SpeedRunner",    "msg": "Confirming plasma rifle crash. Happens specifically in the Neon District zone.", "image": None},
    {"user": "CasualGamer",    "msg": "Why is the blacksmith deleting my items when I try to upgrade them?", "image": None},
    {"user": "ProSniper99",    "msg": "Blacksmith bug is real. Lost my legendary sword trying to upgrade to +5.", "image": "Tpose.png"},
    {"user": "LootGoblin",     "msg": "Fast travel to the Frozen Wastes is broken. Spawns me under the map every time.", "image": None},
    {"user": "GuildMaster_X",  "msg": "Guild bank is inaccessible since the patch. 40 members locked out of shared inventory.", "image": None},
    {"user": "ZeroLatency",    "msg": "Server lag spikes every night around 9PM EST. Unplayable during peak hours.", "image": None},
    {"user": "CryptoKnight",   "msg": "Auction house is showing wrong gold values. Listed item for 1k, sold for 1 gold instead.", "image": None},
    {"user": "NightOwlGamer",  "msg": "Audio completely cuts out after the plasma rifle crash. Have to restart the whole client.", "image": None},
    {"user": "BetaTester_07",  "msg": "This plasma rifle crash was in the beta too. Devs never fixed it, and now it's in live.", "image": None},
    {"user": "SupportMain",    "msg": "Submitted 3 tickets about save corruption. No response in 5 days. Terrible support.", "image": None},
    {"user": "HardcoreHank",   "msg": "Lost 6 hours of progress to save corruption near the Western Obelisk. This is unacceptable.", "image": None},
    {"user": "EconomyWatch",   "msg": "Plasma ammo price spike looks like an exploit. Someone is manipulating the market.", "image": None},
    {"user": "NewPlayerFinn",  "msg": "Just started the game and already hit the plasma rifle crash. Is this game always this buggy?", "image": None},
    {"user": "WikiEditor_Rae", "msg": "Documenting all known bugs: plasma crash, save corruption, blacksmith delete, obelisk warp. List keeps growing.", "image": None},
    {"user": "NeonNinja",      "msg": "Every time I equip the plasma rifle, the game hard crashes. No error message, just closes.", "image": None},
    {"user": "RaidHealer99",   "msg": "My save file corrupted after using the fast travel obelisk near the Western Wastes.", "image": "savefilecorruption.png"},
    {"user": "AngryNoob",      "msg": "Enemy AI just stands completely still during the Cyber-Dragon boss fight. Walked right past them.", "image": "AIfreeze.png"},
    {"user": "SpeedRunner",    "msg": "Found a clipping bug near the Neon District wall. You can phase through it and skip the entire second act.", "image": "wallclipping.png"},
    {"user": "CasualGamer",    "msg": "My character is stuck in the attack animation loop. Just keeps swinging forever, can't move or open menus.", "image": "animationstuck.png"},
    {"user": "ProSniper99",    "msg": "Ragdoll physics on enemies is completely broken. When you kill them they fly 200 meters into the sky.", "image": "ragdoll.png"},
    {"user": "LootGoblin",     "msg": "Invisible wall blocking the entrance to the Shadow Vault dungeon. Can't enter at all since the patch.", "image": "invisiblewall.png"},
    {"user": "GuildMaster_X",  "msg": "Character aggression is bugged. My companion attacks friendly NPCs in every town unprovoked.", "image": "AIaggresion.png"},
    {"user": "ZeroLatency",    "msg": "Dialogue subtitles are completely out of sync with voice acting since the last update. Half a sentence behind.", "image": None},
    {"user": "CryptoKnight",   "msg": "Auction house is showing wrong gold values. Listed my sword for 10k gold, it sold for 10 instead.", "image": None},
    {"user": "NightOwlGamer",  "msg": "Resolution resets to 800x600 every single time I launch the game. Settings don't save at all.", "image": None},
    {"user": "BetaTester_07",  "msg": "Texture pop-in is insane in the Frozen Wastes. Entire mountain ranges just appear out of nowhere 10 feet away.", "image": "texturepopin.png"},
    {"user": "HardcoreHank",   "msg": "Hitbox on the Cyber-Dragon is completely wrong. Attacks are hitting me when they visually miss by a mile.", "image": None},
    {"user": "EconomyWatch",   "msg": "Crafting duplication glitch is live. If you cancel a craft at the exact right frame you keep the materials and get the item.", "image": None},
    {"user": "NewPlayerFinn",  "msg": "Minimap stops updating completely after you die and respawn. Just shows my last position before death.", "image": None},
    {"user": "WikiEditor_Rae", "msg": "Quest marker for The Lost Artifact is pointing to the middle of the ocean. Sent me swimming for 10 minutes.", "image": None},
    {"user": "ShadowBlade_K",  "msg": "Stealth system is broken. Enemies spot me through solid walls and floors even at max stealth stat.", "image": None},
    {"user": "FrameDropFred",  "msg": "FPS tanks to single digits the moment it starts raining in any zone. Completely unplayable weather effect.", "image": None},
    {"user": "VoiceActFan",    "msg": "NPC merchant keeps repeating the same greeting line every single time you click on them. Loops infinitely.", "image": None},
    {"user": "TreasureHunter", "msg": "Loot from chests isn't saving. Opened the same rare chest 3 times after reloading and it keeps respawning.", "image": None},
]


def send_message(item):
    image_path = None
    if item["image"]:
        full_path = os.path.join(IMAGES_FOLDER, item["image"])
        if os.path.exists(full_path):
            image_path = full_path
        else:
            print(f"  ⚠️  Image not found: {full_path}, sending text only.")

    if image_path:
        # Send message with image attachment
        with open(image_path, "rb") as f:
            response = requests.post(
                WEBHOOK_URL,
                data={"payload_json": f'{{"username": "{item["user"]}", "content": "{item["msg"]}"}}'},
                files={"file": (item["image"], f, "image/png")}
            )
    else:
        # Send text-only message
        payload = {
            "username": item["user"],
            "content": item["msg"]
        }
        response = requests.post(WEBHOOK_URL, json=payload)

    return response


print("=" * 50)
print("  Injecting mock data into Discord...")
print("=" * 50)

# Send all messages in mock_data
for index, item in enumerate(mock_data, start=1):
    print(f"[{index}/{len(mock_data)}] Posting as {item['user']}...", end=" ")
    
    response = send_message(item)

    if response.status_code in (200, 204):
        tag = "📎 with image" if item["image"] else "✉️  text only"
        print(f"✅ Sent ({tag})")
    else:
        print(f"❌ Failed (Status: {response.status_code})")

    time.sleep(1)

print("=" * 50)
print("✅ Data injection complete. You may now trigger your mobile app.")
print("=" * 50)