import os
import re
import asyncio
import urllib.parse
import datetime
import aiohttp
from pathlib import Path
from slugify import slugify
from playwright.async_api import async_playwright

START_URL = "https://providencebiblefellowship.com/seminars"

async def get_subpages(page):
    await page.goto(START_URL)
    links = await page.eval_on_selector_all("a", "els => els.map(e => e.href)")
    subpages = sorted(set([link for link in links if "providencebiblefellowship.com/" in link and link.strip("/") != START_URL.strip("/")]))
    return subpages

def sanitize_filename(text):
    return slugify(text or "untitled", lowercase=True, separator="-")

def get_date_slug(text):
    try:
        return datetime.datetime.strptime(text.strip(), "%B %d, %Y").strftime("%Y-%m-%d")
    except Exception:
        return "unknown-date"

async def download_mp3(url, path):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                with open(path, "wb") as f:
                    f.write(await resp.read())
                print(f"⬇️  Downloaded: {path}")
            else:
                print(f"❌ Failed to download: {url}")


async def scrape_media_items(page, base_url):
    slug = urllib.parse.urlparse(base_url).path.strip("/").split("/")[-1]
    folder = os.path.join("downloads", slug)
    os.makedirs(folder, exist_ok=True)

    page_num = 1
    seen_ids = set()

    while True:
        url = f"{base_url}?page={page_num}" if page_num > 1 else base_url
        await page.goto(url)
        await page.wait_for_selector(".media-card", timeout=10000)

        media_buttons = await page.query_selector_all(".media-card")
        print(f"📄 Visiting: {url}\n🔎 Found {len(media_buttons)} media cards")

        # Get media IDs and stop if this page is a repeat
        media_ids = [
            await btn.get_attribute("data-id") or f"idx-{idx}"
            for idx, btn in enumerate(media_buttons)
        ]
        if any(mid in seen_ids for mid in media_ids):
            print(f"🛑 Detected repeating page at page {page_num}. Stopping pagination.")
            break
        seen_ids.update(media_ids)

        for idx, button in enumerate(media_buttons):
            try:
                await button.scroll_into_view_if_needed()
                await button.click()

                await page.wait_for_function(
                    "() => document.querySelector('.media-player video source')?.src?.includes('.mp3')",
                    timeout=10000
                )

                mp3_elem = await page.query_selector(".media-player video source")
                mp3_url = await mp3_elem.get_attribute("src")

                title_el = await page.query_selector(".media-header .media-video-title")
                title = await title_el.inner_text() if title_el else f"untitled-{idx+1}"

                date_el = await page.query_selector(".media-date")
                date = await date_el.inner_text() if date_el else ""

                speaker_el = await page.query_selector(".media-speaker")
                speaker = await speaker_el.inner_text() if speaker_el else "unknown-speaker"

                series_el = await page.query_selector(".media-series")
                series = await series_el.inner_text() if series_el else "unknown-series"

                # Clean values for filename
                clean_title = sanitize_filename(title)
                clean_speaker = sanitize_filename(speaker)
                clean_series = sanitize_filename(series)
                date_slug = get_date_slug(date)

                ext = os.path.splitext(mp3_url)[-1]
                filename = f"{slug}_{date_slug}_{clean_series}_{clean_speaker}_{clean_title}{ext}"
                filepath = os.path.join(folder, filename)

                if os.path.exists(filepath):
                    print(f"✅ Already downloaded: {filename}")
                else:
                    await download_mp3(mp3_url, filepath)
                # Write metadata to a .txt file in the same folder
                metadata_path = os.path.join(folder, "metadata.txt")
                with open(metadata_path, "a", encoding="utf-8") as f:
                    f.write(f"Filename: {filename}\n")
                    f.write(f"Title: {title}\n")
                    f.write(f"Date: {date}\n")
                    f.write(f"Speaker: {speaker}\n")
                    f.write(f"Series: {series}\n")
                    f.write(f"MP3 URL: {mp3_url}\n")
                    f.write("-" * 40 + "\n")

                await asyncio.sleep(1)

            except Exception as e:
                print(f"⚠️  Error processing item {idx+1}: {e}")
                failed_path = os.path.join(folder, "failed.txt")
                with open(failed_path, "a", encoding="utf-8") as f:
                    f.write(f"Item {idx+1} on {url}\n")
                    f.write(f"Error: {str(e)}\n")
                    f.write("-" * 40 + "\n")

        print(f"➡️  Navigating to next page")
        page_num += 1




async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        subpages = await get_subpages(page)
        print(f"🧭 Found {len(subpages)} subpages to process")

        for url in subpages:
            try:
                await scrape_media_items(page, url)
            except Exception as e:
                print(f"❌ Failed to process {url}: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())

