from playwright.sync_api import sync_playwright

SITE_URL = "https://codes.yar.gg/"


def print_ancestors(element, label):
    print(f"\n\n========== {label} ==========")

    for level in range(1, 6):
        html = element.evaluate(
            f"""
            (el) => {{
                let node = el;
                for (let i = 0; i < {level}; i++) {{
                    node = node.parentElement;
                    if (!node) return "";
                }}
                return node.outerHTML;
            }}
            """
        )

        print(f"\n--- PARENT LEVEL {level} ---")
        print(html[:5000])


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    page = browser.new_page()
    page.goto(SITE_URL, wait_until="networkidle")

    # Current first code on page
    first_code = page.locator("input.code-field").first
    print("FIRST CODE:", first_code.input_value())
    print_ancestors(first_code, "FIRST CODE")

    # Known expired code
    expired = page.locator(
        'input[aria-label="Coupon code JPP8WCWPHE"]'
    )

    if expired.count() > 0:
        print("\nFOUND JPP8WCWPHE")
        print_ancestors(expired.first, "JPP8WCWPHE")
    else:
        print("\nCould not find JPP8WCWPHE as input.code-field")

    browser.close()