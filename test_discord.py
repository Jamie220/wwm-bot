import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


# --------------------------------------------------
# Configuration
# --------------------------------------------------

load_dotenv()

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
SITE_URL = "https://codes.yar.gg/"
DATA_FILE = Path("codes.json")


# --------------------------------------------------
# Load Codes
# --------------------------------------------------

def load_codes():
    if not DATA_FILE.exists():
        raise FileNotFoundError("codes.json not found")

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("active_codes", [])


# --------------------------------------------------
# Send All Codes
# --------------------------------------------------

def send_all_codes_to_discord(codes):
    if not WEBHOOK_URL:
        raise ValueError("DISCORD_WEBHOOK_URL not found in .env")

    # Split into groups so the Discord posts stay readable
    chunk_size = 30

    chunks = [
        codes[i:i + chunk_size]
        for i in range(0, len(codes), chunk_size)
    ]

    for index, chunk in enumerate(chunks, start=1):

        code_text = "\n".join(
            f"`{code}`"
            for code in chunk
        )

        payload = {
            "embeds": [
                {
                    "title": (
                        f"🎁 燕云十六声有效兑换码来自大猛1的APP "
                        f"({index}/{len(chunks)})"
                    ),
                    "url": SITE_URL,
                    "description": code_text,
                    "color": 0x5865F2,
                    "footer": {
                        "text": (
                            f"当前有效兑换码：{len(codes)} 个 "
                            f"• 来源：codes.yar.gg"
                        )
                    }
                }
            ]
        }

        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            timeout=30
        )

        response.raise_for_status()

        print(
            f"Sent part {index}/{len(chunks)} "
            f"({len(chunk)} codes)"
        )

    print()
    print(
        f"Successfully sent all {len(codes)} "
        f"active codes to Discord!"
    )


# --------------------------------------------------
# Run
# --------------------------------------------------

if __name__ == "__main__":

    codes = load_codes()

    print(f"Loaded {len(codes)} codes from codes.json")

    send_all_codes_to_discord(codes)