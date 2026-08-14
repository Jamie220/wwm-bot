import json
import os
from datetime import datetime
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
# Get Time
# --------------------------------------------------

def parse_added_date(tooltip):
    """
    Convert:
    'Added to site on 07/26 at 19:40 in local time...'
    into:
    '2026-07-26'
    """

    if not tooltip:
        return None

    try:
        date_part = tooltip.split("Added to site on ")[1].split(" at ")[0]

        month, day = map(int, date_part.split("/"))

        now = datetime.now()
        year = now.year

        # Handle year rollover:
        # e.g. if today is Jan 2027 but code date says 12/30,
        # treat it as Dec 2026.
        if now.month == 1 and month == 12:
            year -= 1

        return f"{year:04d}-{month:02d}-{day:02d}"

    except Exception:
        return None


# --------------------------------------------------
# Get Active Codes
# --------------------------------------------------

def get_active_codes():
    """Get ONLY current active codes from the Active Codes section."""

    print("Opening website...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page()
        page.goto(
            SITE_URL,
            wait_until="networkidle",
            timeout=60000
        )

        print("Website loaded successfully.")

        # IMPORTANT:
        # Only scrape cards inside <section id="codes">
        active_cards = page.locator(
            "section#codes > article.code-card"
        )

        count = active_cards.count()

        print(f"Active cards found: {count}")

        codes = []

        for i in range(count):
            card = active_cards.nth(i)

            # Read the code from THIS card
            code_input = card.locator("input.code-field")

            if code_input.count() == 0:
                continue

            code = code_input.first.input_value().strip()

            if not code:
                continue

            # Read the date from THIS SAME card
            date_button = card.locator("button.code-date")

            added_date = None

            if date_button.count() > 0:
                tooltip = date_button.first.get_attribute(
                    "data-tooltip"
                )

                added_date = parse_added_date(tooltip)

            codes.append({
                "code": code,
                "date": added_date
            })

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
    """Compare current codes against previous codes by code value."""

    # Previous codes may still be stored as plain strings
    previous_code_values = set()

    for item in previous_codes:
        if isinstance(item, dict):
            previous_code_values.add(item.get("code"))
        else:
            previous_code_values.add(item)

    current_code_values = {
        item["code"]
        for item in current_codes
    }

    new_codes = [
        item
        for item in current_codes
        if item["code"] not in previous_code_values
    ]

    removed_codes = [
        code
        for code in previous_code_values
        if code not in current_code_values
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
        f"`{item['code']}` - Release Date: {item['date'] or 'Unknown date'}"
        for item in new_codes
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
    # Helpful if Discord rejects the payload
    if not response.ok:
        print("Discord error:")
        print(response.status_code)
        print(response.text)


    response.raise_for_status()

    print("Discord notification sent successfully!")

def validate_active_codes(codes):
    """Basic safety checks before saving or notifying."""

    if not codes:
        raise RuntimeError(
            "No active codes were scraped. "
            "Stopping to avoid corrupting codes.json."
        )

    code_values = [
        item["code"]
        for item in codes
    ]

    if len(code_values) != len(set(code_values)):
        raise RuntimeError(
            "Duplicate active codes detected. "
            "Stopping for safety."
        )

    # Safety check against obviously incomplete page loads
    if len(codes) < 20:
        raise RuntimeError(
            f"Only {len(codes)} active codes were scraped. "
            "This looks abnormal, so the run is being stopped."
        )

    return True

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

    validate_active_codes(current_codes)

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

        for item in new_codes:
            print(f"  + {item['code']} - {item['date']}")

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