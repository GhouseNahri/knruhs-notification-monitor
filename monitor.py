import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urldefrag, urlparse

import requests
from bs4 import BeautifulSoup

PAGE_URL = os.getenv(
    "TARGET_URL",
    "https://www.knruhs.telangana.gov.in/admission-notification/",
)
STATE_FILE = os.getenv("STATE_FILE", "state.json")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
BASELINE_ONLY = os.getenv("BASELINE_ONLY", "false").lower() == "true"
MAX_LINKS = int(os.getenv("MAX_LINKS", "500"))
TIMEOUT = 25
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KNRUHSNoticeMonitor/1.0; +https://github.com/)"
}

def log(message):
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {message}", flush=True)

def canonical_url(url):
    url = urldefrag(url)[0].strip()
    return url

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        log(f"Could not read state file ({exc}); treating this as first run.")
        return {}

def save_state(state):
    temp = STATE_FILE + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(temp, STATE_FILE)

def fetch_page():
    response = requests.get(PAGE_URL, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    if not response.text or len(response.text) < 200:
        raise RuntimeError("Page response looks unexpectedly short; refusing to update saved state.")
    return response.text, response.url

def extract_notices(html, final_url):
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for a in soup.select("a[href]"):
        title = " ".join(a.get_text(" ", strip=True).split())
        href = a.get("href", "").strip()
        if not title or not href or href.startswith(("javascript:", "mailto:", "tel:")):
            continue
        url = canonical_url(urljoin(final_url, href))
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            continue

        # Ignore navigation/social links with no notice-like content. Keep document links
        # and links whose labels look like a notice/admission/counselling/result/update.
        path = parsed.path.lower()
        label = title.lower()
        is_document = bool(re.search(r"\.(pdf|docx?|xlsx?|zip)(?:$|\?)", path))
        is_notice_like = bool(re.search(
            r"\b(notification|notice|admission|counselling|counseling|merit|"
            r"provisional|final|schedule|time table|timetable|allotment|result|"
            r"web options|certificate|application|prospectus|202[4-9]|20[3-9]\d)\b",
            label + " " + path
        ))
        if not (is_document or is_notice_like):
            continue

        # Stable identity is the absolute URL; title changes on the same URL won't duplicate
        # an alert. URLs are stored with their visible title and first-seen timestamp.
        found[url] = {
            "title": title[:500],
            "url": url,
        }
        if len(found) >= MAX_LINKS:
            break

    # A small page fingerprint helps diagnose changes that don't add matching links.
    text = " ".join(soup.get_text(" ", strip=True).split())
    page_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return found, page_hash

def telegram_send(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Telegram secrets are missing: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
    endpoint = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(
        endpoint,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message[:4000],
            "disable_web_page_preview": True,
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API error: {payload}")
    return True

def main():
    log(f"Checking {PAGE_URL}")
    html, final_url = fetch_page()
    current, page_hash = extract_notices(html, final_url)
    if not current:
        raise RuntimeError(
            "No notice-like links were found. To avoid accidentally resetting state, "
            "the monitor stopped. Inspect the page HTML/selectors before continuing."
        )

    state = load_state()
    old_notices = state.get("notices", {})
    old_hash = state.get("page_hash")
    first_run = not isinstance(old_notices, dict) or not old_notices

    if first_run or BASELINE_ONLY:
        new_state = {
            "target_url": PAGE_URL,
            "last_checked_utc": datetime.now(timezone.utc).isoformat(),
            "page_hash": page_hash,
            "notices": {
                url: {
                    **notice,
                    "first_seen_utc": datetime.now(timezone.utc).isoformat(),
                }
                for url, notice in current.items()
            },
        }
        save_state(new_state)
        if first_run:
            log(f"First run: saved baseline of {len(current)} notice/document links; no alerts sent.")
        else:
            log(f"Baseline refreshed with {len(current)} links; no alerts sent.")
        return

    new_urls = sorted(set(current) - set(old_notices))
    now = datetime.now(timezone.utc).isoformat()
    merged = dict(old_notices)
    for url, notice in current.items():
        if url not in merged:
            merged[url] = {**notice, "first_seen_utc": now}
        else:
            # Update changed display titles while retaining the original first-seen timestamp.
            merged[url] = {**merged[url], **notice}

    # Alert before saving the state. If Telegram fails, the workflow fails and the next
    # scheduled run retries the alert instead of silently losing it.
    if new_urls:
        lines = [
            "🔔 KNRUHS admission page: new link(s) detected",
            "",
        ]
        for url in new_urls[:20]:
            item = current[url]
            lines.append(f"• {item['title']}\n{url}")
        if len(new_urls) > 20:
            lines.append(f"\n…and {len(new_urls) - 20} more new links.")
        lines.append(f"\nChecked: {now}")
        telegram_send("\n".join(lines))
        log(f"Sent Telegram alert for {len(new_urls)} new link(s).")
    else:
        log(f"No new notice/document links. Tracked {len(current)} matching links.")
        if old_hash != page_hash:
            log("The page text changed, but no new matching links were detected.")

    save_state({
        "target_url": PAGE_URL,
        "last_checked_utc": now,
        "page_hash": page_hash,
        "notices": merged,
    })

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"ERROR: {exc}")
        sys.exit(1)
