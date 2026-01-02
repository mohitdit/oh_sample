from playwright.async_api import async_playwright


async def get_stealth_browser(headless=True):
    playwright = await async_playwright().start()

    browser = await playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )

    context = await browser.new_context(
        accept_downloads=True,   # ✅ ENABLE DOWNLOADS HERE
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )

    page = await context.new_page()
    return browser, context, page
