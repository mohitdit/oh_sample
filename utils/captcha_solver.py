import asyncio
from playwright.async_api import async_playwright
from captcha_solver import CaptchaSolver

CAPTCHA_POST_URL = "http://fasttypers.org/imagepost.ashx"
CAPTCHA_KEY = "14AMYQ1DPJPOJ8YF1D7AJ82JIKVUEFMG9LFWIQ5P"

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto(
            "https://ohtrafficdata.dps.ohio.gov/CrashRetrieval",
            timeout=60000
        )

        # wait for captcha
        captcha_img = await page.wait_for_selector("img.captchaImage", timeout=30000)
        captcha_base64 = await captcha_img.get_attribute("src")

        solver = CaptchaSolver(CAPTCHA_POST_URL, CAPTCHA_KEY)

        if not solver.solve_captcha(captcha_base64):
            raise Exception(f"Captcha failed: {solver.last_post_state}")

        captcha_text = solver.last_response_text
        print("✅ Captcha solved:", captcha_text)

        # fill captcha
        await page.fill('input[type="text"]', captcha_text)

        # submit form
        await page.click('button[type="submit"]')

        await page.wait_for_load_state("networkidle")
        await browser.close()

asyncio.run(run())
