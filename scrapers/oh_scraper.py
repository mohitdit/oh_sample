import os
import json
import asyncio
from utils.captcha_solver import solve_captcha
from utils.browser_manager import get_stealth_browser
from utils.logger import log
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from scrapers.base_scraper import BaseScraper

# Define the cookie file path
COOKIE_FILE = "wcca_cookies.json"

class OhioScraper(BaseScraper):

    async def detect_and_solve_captcha(self, page):
        log.info("🔍 Checking for CAPTCHA...")

        # --- STEP 1: DETECT CAPTCHA PAGE ---
        # Instead of looking for the image immediately, look for the warning text.
        # The screenshot shows the text: "Please complete the CAPTCHA."
        try:
            # We use a short timeout because we don't want to slow down normal scraping
            captcha_present = await page.wait_for_selector("text=Please complete the CAPTCHA", timeout=3000)
        except:
            captcha_present = None

        # If the text isn't there, check if the image exists anyway (just to be safe)
        if not captcha_present:
            if await page.is_visible("img#captcha"):
                captcha_present = True
            else:
                log.info("✅ No CAPTCHA detected.")
                return False 

        log.warning("⚠ CAPTCHA Page detected! Initiating solver...")

        # --- STEP 2: REVEAL THE IMAGE ---
        # The user noted we must click "Click here" for the image to appear.
        is_image_visible = await page.is_visible("img#captcha")
        
        if not is_image_visible:
            log.info("🖼 CAPTCHA image hidden. Clicking trigger link...")
            try:
                # Click the "Click here" link inside the text "Click here if CAPTCHA..."
                await page.click("text=Click here", timeout=3000)
                
                # Now wait for the image to actually load
                await page.wait_for_selector("img#captcha", state="visible", timeout=5000)
                log.info("✅ CAPTCHA image revealed.")
            except Exception as e:
                log.error(f"❌ Failed to click trigger link or load image: {e}")
                return False

        # --- STEP 3: CAPTURE & SOLVE ---
        img_element = await page.query_selector("img#captcha")
        if not img_element:
            log.error("❌ CAPTCHA element not found in DOM.")
            return False
            
        img_bytes = await img_element.screenshot()

        # Send to DeathByCaptcha
        solved_text = await solve_captcha(img_bytes)
        log.info(f"🧩 CAPTCHA returned: {solved_text}")

        if not solved_text:
            log.error("❌ Failed to solve CAPTCHA (Empty response)")
            return False

        # --- STEP 4: SUBMIT ---
        await page.fill("input#captchaAnswer", solved_text)
        await page.click("button[type=submit]")
        
        # Wait for the "Please complete" text to disappear to confirm success
        try:
            await page.wait_for_function("() => !document.body.innerText.includes('Please complete the CAPTCHA')", timeout=5000)
        except:
            log.warning("Page did not navigate away immediately. Solver might have failed or site is slow.")

        return True

    async def run_scraper(self):
        browser, context, page = await get_stealth_browser(False)

        case_url = self.build_case_url()
        docket = f"{self.config['docketYear']}{self.config['docketType']}{self.config['docketNumber']}"

        log.info(f"--- Starting scrape for {docket} ---")

        # --- STEP 1: LOAD COOKIES ---
        if os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                    await context.add_cookies(cookies)
                log.info(f"🍪 Loaded {len(cookies)} cookies from session file.")
            except Exception as e:
                log.error(f"Failed loading cookies: {e}")

        # --- STEP 2: NAVIGATE ---
        try:
            await page.goto(case_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            log.error(f"Navigation failed: {e}")
            await browser.close()
            return None

        # --- STEP 3: HANDLE CAPTCHA ---
        # We try to solve up to 3 times if it fails
        max_retries = 3
        for attempt in range(max_retries):
            # Check if we are already in (Summary exists)
            if await page.query_selector("text=Case Summary"):
                break
            
            # Check for Captcha
            is_captcha = await self.detect_and_solve_captcha(page)
            if is_captcha:
                await page.wait_for_timeout(3000) # Give site time to process
            else:
                # If no captcha and no summary, maybe just slow loading or 404
                break

        # --- STEP 4: VERIFY SUCCESS & SAVE COOKIES ---
        try:
            await page.wait_for_selector("text=Case Summary", timeout=15000)
            log.info("✅ Case Summary Loaded.")

            # *** CRITICAL FIX: SAVE COOKIES ***
            # Save the valid session so next time we skip captcha
            cookies = await context.cookies()
            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            log.info("💾 Session cookies saved for future use.")

        except PlaywrightTimeoutError:
            log.error("❌ Could not load Case Summary. Captcha failed or Case Unavailable.")
            # If we see "Your request could not be processed", return that html
            html = await page.content()
            await browser.close()
            return {"docket": docket, "html": html, "status": "failed"}

        html = await page.content()
        
        await context.close()
        await browser.close()

        return {"docket": docket, "html": html, "status": "ok"}