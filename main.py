import asyncio
from datetime import date
from pathlib import Path
import aiohttp
from calendar import monthrange

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from utils.browser_manager import get_stealth_browser
from utils.logger import log
from utils.captcha_solver import CaptchaSolver
import base64


# MODE CONFIGURATION (ONLY CHANGE THESE)

MODE = "PAST"          # "PAST" or "PRESENT"

# Past year (FULL YEAR)

# MODE = "PAST"
# PAST_YEAR = 2022

# Present / custom range

# MODE = "PRESENT"
# START_DATE = date(2025, 2, 1)
# END_DATE   = date(2025, 4, 15)

# ---- PAST MODE ----
PAST_YEAR = 2023       # Used only when MODE = "PAST"

# ---- PRESENT MODE ----
START_DATE = date(2025, 12, 18)
END_DATE   = date(2025, 12, 20)


# =====================================================
# COUNTY CONTROL
# =====================================================
# None            -> ALL counties
# [1, 88]         -> First & last
# [1, 12, 45]     -> Custom counties

COUNTY_TEST_IDS = None   #  Change this when testing



# SITE CONFIG

TARGET_URL = "https://ohtrafficdata.dps.ohio.gov/CrashRetrieval"
REPORT_POST_BASE = "https://ohtrafficdata.dps.ohio.gov/CrashRetrieval/OhioCrashReportRetrieval"

# DeathByCaptcha credentials
DBC_USERNAME = "hr@dharani.co.in"
DBC_PASSWORD = "Dh@r@ni@gnt99!"

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# DATE RANGE GENERATOR

def generate_month_ranges():
    ranges = []

    if MODE == "PAST":
        year = PAST_YEAR

        for month in range(1, 13):
            last_day = monthrange(year, month)[1]

            ranges.append((
                f"{month:02d}/01/{year} 12:00:00 AM",
                f"{month:02d}/{last_day}/{year} 11:59:59 PM",
                year,
                month
            ))

    elif MODE == "PRESENT":
        year = START_DATE.year
        month = START_DATE.month

        while (year, month) <= (END_DATE.year, END_DATE.month):
            month_start = date(year, month, 1)
            last_day = monthrange(year, month)[1]
            month_end = date(year, month, last_day)

            if month_start < START_DATE:
                month_start = START_DATE
            if month_end > END_DATE:
                month_end = END_DATE

            ranges.append((
                month_start.strftime("%m/%d/%Y 12:00:00 AM"),
                month_end.strftime("%m/%d/%Y 11:59:59 PM"),
                year,
                month
            ))

            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
    else:
        raise ValueError("MODE must be 'PAST' or 'PRESENT'")

    return ranges

# RETURN TO SEARCH PAGE

async def return_to_search(page):
    log.info("↩️ Returning to search page")
    await page.click("text=Back to Search")
    await page.wait_for_selector("#txtCrashStartDate", timeout=30000)
    await page.wait_for_timeout(1000)

# PAGINATION

async def download_all_pages(page):
    page_index = 1

    while True:
        log.info(f"📄 Processing results page {page_index}")
        await download_all_reports(page)

        next_button = page.locator("ul.pagination li:not(.disabled) a", has_text=">")

        if await next_button.count() == 0:
            log.info("📘 No more pages")
            break

        await next_button.first.click()
        await page.wait_for_selector("#mySearchTable tbody tr.selectable", timeout=30000)
        await page.wait_for_timeout(1200)

        page_index += 1

# PDF DOWNLOAD LOGIC

async def download_all_reports(page):
    log.info("📄 Scanning results table")

    rows = page.locator("#mySearchTable tbody tr.selectable")
    count = await rows.count()
    log.info(f"📊 Found {count} reports")

    for i in range(count):
        row = rows.nth(i)

        crash_number = (await row.locator("td").nth(1).inner_text()).strip()
        document_number = (await row.locator("td").nth(8).inner_text()).strip()

        file_path = DOWNLOAD_DIR / f"{document_number}.pdf"

        if file_path.exists():
            log.info(f"⏭️ Already exists: {file_path.name}")
            continue

        log.info(f"⬇️ Downloading PDF for crash {crash_number}")

        form = row.locator("form")

        token = await form.locator("input[name='__RequestVerificationToken']").get_attribute("value")
        report_id = await form.locator("input[name='id']").get_attribute("value")

        button = form.locator("button[type='submit']")
        button_name = await button.get_attribute("name")

        cookies = await page.context.cookies()
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{REPORT_POST_BASE}/GetReport",
                data={
                    "__RequestVerificationToken": token,
                    "id": report_id,
                    button_name: ""
                },
                headers={
                    "Cookie": cookie_header,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": page.url,
                    "Accept": "application/pdf",
                },
            ) as resp:

                content_type = resp.headers.get("Content-Type", "")
                log.info(f"📦 Response Content-Type: {content_type}")

                if "pdf" not in content_type.lower():
                    log.error("❌ Not a PDF — skipping")
                    continue

                pdf_bytes = await resp.read()

        file_path.write_bytes(pdf_bytes)
        log.info(f"✅ Saved: {file_path}")


# MAIN SCRAPER

async def main():
    log.info("🚀 Starting Playwright browser")

    browser, context, page = await get_stealth_browser(headless=False)

    try:
        await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
        log.info("✅ Page loaded")

        date_ranges = generate_month_ranges()

        for start_str, end_str, year, month in date_ranges:
            log.info(f"📅 Processing {year}-{month:02d}: {start_str} → {end_str}")

            # Set Start Date
            await page.click("#txtCrashStartDate")
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.fill("#txtCrashStartDate", start_str)
            await page.keyboard.press("Tab")

            # Set End Date
            await page.click("#txtCrashEndDate")
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.fill("#txtCrashEndDate", end_str)
            await page.keyboard.press("Tab")

            county_options = await page.locator("#ddlCounties option").all()

            for county in county_options:
                county_value = await county.get_attribute("value")
                county_text = (await county.text_content()).strip()

                if not county_value:
                    continue

                if COUNTY_TEST_IDS is not None and int(county_value) not in COUNTY_TEST_IDS:
                    continue

                log.info(f"🏛️ County: {county_text}")
                await page.select_option("#ddlCounties", county_value)
                await page.wait_for_timeout(1500)

                log.info("🔍 Clicking Search — will solve CAPTCHA if it appears")
                await page.click("#btnSearch")
                
                # Wait a moment for page to load (might show CAPTCHA or results)
                await page.wait_for_timeout(3000)
                
                # Try to solve captcha automatically if it appears
                try:
                    # Look for the captcha label to confirm CAPTCHA page loaded
                    captcha_label = await page.wait_for_selector("text=Enter the text from the image:", timeout=10000)
                    
                    if captcha_label:
                        log.info("🔍 CAPTCHA form detected, locating image...")
                        
                        # Wait for image to fully load
                        await page.wait_for_timeout(2000)
                        
                        # Find the CAPTCHA image by its class name (from the HTML)
                        captcha_img = await page.query_selector("img.captchaImage")
                        
                        if not captcha_img:
                            log.error("❌ Could not find captcha image with class 'captchaImage'")
                            input("⛔ Solve CAPTCHA manually in browser, then press ENTER here...")
                            await page.wait_for_timeout(1500)
                            continue
                        
                        # Get the base64 src directly
                        captcha_src = await captcha_img.get_attribute("src")
                        
                        if not captcha_src or "data:image" not in captcha_src:
                            log.error("❌ Invalid captcha src attribute")
                            input("⛔ Solve CAPTCHA manually in browser, then press ENTER here...")
                            await page.wait_for_timeout(1500)
                            continue
                        
                        log.info("🔍 Found CAPTCHA image, sending to solver...")
                        
                        # Initialize solver
                        solver = CaptchaSolver(DBC_USERNAME, DBC_PASSWORD)
                        
                        # Check balance
                        balance = solver.get_balance()
                        log.info(f"💰 DBC Balance: ${balance:.2f}")
                        
                        if balance <= 0:
                            log.error("❌ Insufficient DBC balance")
                            input("⛔ Add balance to DeathByCaptcha account, then press ENTER...")
                            continue
                        
                        # Extract base64 data
                        try:
                            captcha_src = captcha_src.strip()
                            
                            if ',' not in captcha_src or 'data:image' not in captcha_src:
                                log.error(f"❌ Invalid captcha src format")
                                input("⛔ Solve CAPTCHA manually in browser, then press ENTER here...")
                                await page.wait_for_timeout(1500)
                                continue
                            
                            parts = captcha_src.split(',', 1)
                            if len(parts) != 2:
                                log.error(f"❌ Could not split captcha src by comma")
                                input("⛔ Solve CAPTCHA manually in browser, then press ENTER here...")
                                await page.wait_for_timeout(1500)
                                continue
                            
                            base64_data = parts[1].strip()
                            log.info(f"🔍 Base64 data length: {len(base64_data)}")
                            
                            # Decode base64
                            captcha_bytes = base64.b64decode(base64_data)
                            log.info(f"📤 Captcha image size: {len(captcha_bytes)} bytes")
                            
                            # Validate size
                            if len(captcha_bytes) > 50000:
                                log.error(f"❌ Image too large ({len(captcha_bytes)} bytes)")
                                input("⛔ Solve CAPTCHA manually in browser, then press ENTER here...")
                                await page.wait_for_timeout(1500)
                                continue
                            
                            if len(captcha_bytes) < 500:
                                log.error(f"❌ Image too small ({len(captcha_bytes)} bytes)")
                                input("⛔ Solve CAPTCHA manually in browser, then press ENTER here...")
                                await page.wait_for_timeout(1500)
                                continue
                            
                            # Solve with retry logic
                            max_retries = 3
                            captcha_solved = False
                            
                            for attempt in range(max_retries):
                                try:
                                    log.info(f"🔄 Attempt {attempt + 1}/{max_retries} to solve captcha...")
                                    captcha_solved = await solver.solve_captcha_from_bytes(captcha_bytes)
                                    
                                    if captcha_solved:
                                        break
                                    else:
                                        log.warning(f"⚠️ Attempt {attempt + 1} failed, retrying...")
                                        await asyncio.sleep(2)
                                        
                                except Exception as e:
                                    log.error(f"❌ Attempt {attempt + 1} error: {str(e)[:100]}")
                                    if attempt < max_retries - 1:
                                        await asyncio.sleep(3)
                                    continue
                            
                            if captcha_solved:
                                captcha_text = solver.last_response_text.strip()
                                log.info(f"✅ CAPTCHA solved: '{captcha_text}' (length: {len(captcha_text)})")
                                
                                # Validate length (should be 6 based on HTML maxlength="6")
                                if len(captcha_text) != 6:
                                    log.warning(f"⚠️ CAPTCHA text length is {len(captcha_text)}, expected 6")
                                
                                # Find the input field by ID (from HTML: id="txtCaptcha")
                                captcha_input = await page.query_selector("#txtCaptcha")
                                
                                if captcha_input:
                                    # Clear and fill
                                    await captcha_input.click()
                                    await page.keyboard.press("Control+A")
                                    await page.keyboard.press("Backspace")
                                    await page.wait_for_timeout(300)
                                    
                                    await captcha_input.fill(captcha_text)
                                    log.info(f"✅ CAPTCHA text '{captcha_text}' entered")
                                    
                                    # Wait a moment then press Enter to submit the form
                                    await page.wait_for_timeout(1000)
                                    await captcha_input.press("Enter")
                                    log.info("✅ Pressed Enter to submit captcha")
                                else:
                                    log.error("❌ Could not find captcha input field #txtCaptcha")
                                    input("⛔ Fill in CAPTCHA manually in browser, then press ENTER here...")
                            else:
                                log.error(f"❌ CAPTCHA solving failed after {max_retries} attempts")
                                input("⛔ Solve CAPTCHA manually in browser, then press ENTER here...")
                                
                        except Exception as e:
                            log.error(f"❌ Error processing captcha image: {e}")
                            import traceback
                            traceback.print_exc()
                            input("⛔ Solve CAPTCHA manually in browser, then press ENTER here...")
                    else:
                        log.info("✅ No CAPTCHA detected, proceeding...")
                        
                except Exception as e:
                    log.warning(f"⚠️ CAPTCHA detection error: {e}")
                    input("⛔ Solve CAPTCHA manually in browser, then press ENTER here...")
                
                await page.wait_for_timeout(3000)

                no_results = page.locator("text=No results found matching your criteria")
                if await no_results.is_visible():
                    log.info("🚫 No results found — next county")
                    await return_to_search(page)
                    continue

                await page.wait_for_selector("#mySearchTable", timeout=30000)
                await download_all_pages(page)
                await return_to_search(page)

        log.info("✅ All counties completed")

    except PlaywrightTimeoutError:
        log.error("⏰ Page timeout")
    except Exception as e:
        log.exception(f"❌ Error: {e}")
    finally:
        log.info("🛑 Closing browser")
        await context.close()
        await browser.close()

# ENTRY POINT

if __name__ == "__main__":
    asyncio.run(main())
