import email.utils
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).parent
FEEDS_PATH = ROOT / "feeds.json"
STATE_DIR = ROOT / ".state"
STATE_PATH = STATE_DIR / "seen.json"
MAX_MESSAGE_LENGTH = 1900
MAX_ITEMS_PER_FEED = 2
FIRST_RUN_LOOKBACK_HOURS = 6


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def clean_text(value):
    if not value:
        return ""
    parser = TextExtractor()
    try:
        parser.feed(value)
        text = " ".join(parser.parts)
    except Exception:
        text = value
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def child_text(element, names):
    for child in list(element):
        local_name = child.tag.rsplit("}", 1)[-1].lower()
        if local_name in names:
            value = clean_text("".join(child.itertext()))
            if value:
                return value
    return ""


def item_link(element):
    for child in list(element):
        if child.tag.rsplit("}", 1)[-1].lower() == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            value = (child.text or "").strip()
            if value:
                return value
    return ""


def parse_date(value):
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_feed(xml_bytes, feed_name):
    root = ET.fromstring(xml_bytes)
    elements = [el for el in root.iter() if el.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}]
    results = []
    for element in elements:
        title = child_text(element, {"title"})
        link = item_link(element)
        guid = child_text(element, {"guid", "id"}) or link or title
        date_text = child_text(element, {"pubdate", "published", "updated", "date"})
        published = parse_date(date_text)
        if title and link and guid:
            results.append({
                "id": f"{feed_name}|{guid}",
                "title": title,
                "link": link,
                "published": published,
                "source": feed_name,
            })
    return results


def load_seen():
    if not STATE_PATH.exists():
        return set()
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return set(payload.get("seen", []))
    except (OSError, json.JSONDecodeError, AttributeError):
        return set()


def save_seen(seen):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    # Keep a bounded history so the cache remains small.
    STATE_PATH.write_text(json.dumps({"seen": list(sorted(seen))[-5000:]}, ensure_ascii=False), encoding="utf-8")


def discord_post(webhook_url, content):
    body = json.dumps({"content": content, "allowed_mentions": {"parse": []}}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "CapInvestissementRSS/1.0"},
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                if response.status not in (200, 204):
                    raise RuntimeError(f"Discord returned HTTP {response.status}")
                return
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 2:
                try:
                    retry_after = float(json.loads(exc.read().decode("utf-8")).get("retry_after", 2))
                except Exception:
                    retry_after = 2
                time.sleep(min(max(retry_after, 1), 10))
                continue
            raise RuntimeError(f"Discord returned HTTP {exc.code}") from None


def format_message(item):
    published = item["published"]
    date_part = f" · {published:%d/%m/%Y %H:%M} UTC" if published else ""
    content = f"**{item['source']}**{date_part}\n{item['title']}\n{item['link']}"
    return content[:MAX_MESSAGE_LENGTH]


def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("Missing required Actions secret: DISCORD_WEBHOOK_URL", file=sys.stderr)
        return 2
    parsed_url = urllib.parse.urlparse(webhook_url)
    if parsed_url.scheme != "https" or parsed_url.hostname != "discord.com" or not parsed_url.path.startswith("/api/webhooks/"):
        print("DISCORD_WEBHOOK_URL must be a Discord HTTPS webhook URL", file=sys.stderr)
        return 2

    feeds = json.loads(FEEDS_PATH.read_text(encoding="utf-8"))
    if not isinstance(feeds, list) or not feeds:
        print("feeds.json must contain at least one feed", file=sys.stderr)
        return 2

    seen = load_seen()
    first_run = not seen
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FIRST_RUN_LOOKBACK_HOURS)
    new_seen = set(seen)
    pending = []
    errors = []

    for feed in feeds:
        name = str(feed.get("name", "RSS")).strip() or "RSS"
        url = str(feed.get("url", "")).strip()
        if not url.startswith("https://"):
            errors.append(f"{name}: feed URL must use HTTPS")
            continue
        req = urllib.request.Request(url, headers={"User-Agent": "CapInvestissementRSS/1.0 (RSS reader)"})
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                entries = parse_feed(response.read(), name)
            entries.sort(key=lambda item: item["published"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            for item in entries:
                if item["id"] in seen:
                    continue
                new_seen.add(item["id"])
                if first_run and item["published"] and item["published"] < cutoff:
                    continue
                pending.append(item)
        except Exception as exc:
            # Do not print request URLs or webhook details into public workflow logs.
            errors.append(f"{name}: {type(exc).__name__}")

    pending.sort(key=lambda item: item["published"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    per_feed_count = {}
    for item in pending:
        if per_feed_count.get(item["source"], 0) >= MAX_ITEMS_PER_FEED:
            continue
        discord_post(webhook_url, format_message(item))
        per_feed_count[item["source"]] = per_feed_count.get(item["source"], 0) + 1

    save_seen(new_seen)
    if errors:
        print("Some feeds could not be read: " + "; ".join(errors))
    print(f"Published {sum(per_feed_count.values())} new item(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
