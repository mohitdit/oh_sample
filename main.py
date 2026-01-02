import asyncio
from datetime import date
from pathlib import Path
import aiohttp
from calendar import monthrange

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from utils.browser_manager import get_stealth_browser
from utils.logger import log


# MODE CONFIGURATION (ONLY CHANGE THESE)

MODE = "PRESENT"          # "PAST" or "PRESENT"

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
START_DATE = date(2025, 1, 10)
END_DATE   = date(2025, 7, 20)



# SITE CONFIG

TARGET_URL = "https://ohtrafficdata.dps.ohio.gov/CrashRetrieval"
REPORT_POST_BASE = "https://ohtrafficdata.dps.ohio.gov/CrashRetrieval/OhioCrashReportRetrieval"

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

                log.info(f"🏛️ County: {county_text}")
                await page.select_option("#ddlCounties", county_value)
                await page.wait_for_timeout(1500)

                log.info("🔍 Clicking Search — solve CAPTCHA manually")
                await page.click("#btnSearch")
                input("⛔ Solve CAPTCHA in browser, then press ENTER here...")

                await page.wait_for_timeout(1500)

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
