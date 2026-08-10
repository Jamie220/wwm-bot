import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright


# --------------------------------------------------
# Configuration
# --------------------------------------------------

load_dotenv()

SITE_URL = "https://codes.yar.gg/"
DATA_FILE = Path("codes.json")
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


# --------------------------------------------------
# Get Active Codes
# --------------------------------------------------

def get_active_codes():
    """Get the current Active Codes from codes.yar.gg."""

    print("Opening website...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page()
        page.goto(SITE_URL, wait_until="networkidle")

        print("Website loaded successfully.")

        code_inputs = page.locator("input.code-field")
        count = code_inputs.count()

        codes = []

        for i in range(count):
            value = code_inputs.nth(i).input_value().strip()

            if value:
                codes.append(value)

        browser.close()

    return codes


# --------------------------------------------------
# Load Previous Codes
# --------------------------------------------------

def load_previous_codes():
    """Load the previously saved Active Codes."""

    if not DATA_FILE.exists():
        print("No previous codes.json found.")
        return []

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("active_codes", [])


# --------------------------------------------------
# Save Current Codes
# --------------------------------------------------

def save_codes(codes):
    """Save the latest Active Codes."""

    data = {
        "active_codes": codes
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(codes)} codes to {DATA_FILE}")


# --------------------------------------------------
# Compare Codes
# --------------------------------------------------

def compare_codes(current_codes, previous_codes):
    """Compare current codes with the previous saved list."""

    new_codes = [
        code for code in current_codes
        if code not in previous_codes
    ]

    removed_codes = [
        code for code in previous_codes
        if code not in current_codes
    ]

    return new_codes, removed_codes


# --------------------------------------------------
# Send Discord Notification
# --------------------------------------------------

def send_discord_notification(new_codes, total_active):
    """Send newly discovered codes to Discord."""

    if not WEBHOOK_URL:
        raise ValueError("DISCORD_WEBHOOK_URL not found in .env")

    code_text = "\n".join(
        f"`{code}`"
        for code in new_codes
    )

    payload = {
        "embeds": [
            {
                "title": "✨ New WWM Redemption Code",
                "url": SITE_URL,
                "description": (
                    f"🎁 **Found {len(new_codes)} new code(s)!**\n\n"
                    f"{code_text}\n\n"
                    f"📊 **Total active codes:** {total_active}"
                ),
                "color": 0x5865F2,
                "footer": {
                    "text": "Source: codes.yar.gg"
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

    print("Discord notification sent successfully!")


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    print("================================")
    print("WWM Code Tracker started")
    print("================================")

    previous_codes = load_previous_codes()

    print(f"Previous active codes: {len(previous_codes)}")

    current_codes = get_active_codes()

    print(f"Current active codes: {len(current_codes)}")

    new_codes, removed_codes = compare_codes(
        current_codes,
        previous_codes
    )

    print("\n================================")
    print("RESULT")
    print("================================")

    if new_codes:
        print(f"\nNew codes found: {len(new_codes)}")

        for code in new_codes:
            print(f"  + {code}")

        # Send Discord notification
        send_discord_notification(
            new_codes,
            len(current_codes)
        )

    else:
        print("\nNo new codes found.")

    if removed_codes:
        print(f"\nCodes no longer active: {len(removed_codes)}")

        for code in removed_codes:
            print(f"  - {code}")

    else:
        print("No codes were removed.")

    # Update codes.json after everything succeeds
    save_codes(current_codes)

    print("\nCheck completed.")


if __name__ == "__main__":
    main()