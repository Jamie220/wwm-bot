from playwright.sync_api import sync_playwright

SITE_URL = "https://codes.yar.gg/"


def inspect_code():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page()
        page.goto(SITE_URL, wait_until="networkidle")

        # Find the first active code
        code = page.locator("input.code-field").first

        print("CODE:")
        print(code.input_value())

        print("\nPARENT HTML:")
        print(
            code.evaluate(
                "(el) => el.parentElement.outerHTML"
            )
        )

        print("\nGRANDPARENT HTML:")
        print(
            code.evaluate(
                "(el) => el.parentElement.parentElement.outerHTML"
            )
        )

        browser.close()


if __name__ == "__main__":
    inspect_code()