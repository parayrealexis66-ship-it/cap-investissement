"""Publish new RSS/Atom headlines to a Discord webhook without third-party packages."""
import argparse
import email.utils
import html
import hashlib
import json
import os
import re
import sys
import uuid
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

if __name__ == '__main__':
    sys.modules['rss_to_discord'] = sys.modules[__name__]

ROOT = Path(__file__).parent
FEEDS_PATH = ROOT / "feeds.json"
STATE_PATH = ROOT / ".state" / "seen.json"
MAX_ITEMS_PER_FEED = 2
FIRST_RUN_LOOKBACK_HOURS = 6
UTC = timezone.utc
PARIS = ZoneInfo("Europe/Paris")
MAX_DAILY_MESSAGES = 8
MAX_AGE_HOURS = 48


class FeedError(Exception):
    """A public source could not be read."""


class PublishError(Exception):
    """A safe error message that never contains the webhook URL."""


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def clean_text(value):
    parser = TextExtractor()
    parser.feed(value or "")
    return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()


def local_name(element):
    return element.tag.rsplit("}", 1)[-1].lower()


def child_text(element, names):
    for name in names:
        for child in element:
            if local_name(child) == name:
                value = clean_text("".join(child.itertext()))
                if value:
                    return value
    return ""


def item_link(element):
    for child in element:
        if local_name(child) == "link" and child.attrib.get("rel", "alternate") == "alternate":
            value = (child.attrib.get("href") or child.text or "").strip()
            parsed = urllib.parse.urlparse(value)
            if parsed.scheme in ("https", "http") and parsed.hostname:
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
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_feed(xml_bytes, feed_name):
    root = ET.fromstring(xml_bytes)
    if local_name(root) not in {"rss", "feed", "rdf"}:
        raise FeedError("La réponse n'est pas un flux RSS ou Atom")
    results = []
    for element in root.iter():
        if local_name(element) not in {"item", "entry"}:
            continue
        title = child_text(element, ("title",))
        link = item_link(element)
        guid = child_text(element, ("guid", "id")) or link
        published = parse_date(child_text(element, ("pubdate", "published", "date", "updated")))
        if title and link:
            results.append({"id": guid, "title": title, "link": link,
                            "published": published, "source": feed_name})
    return results


def fetch_feed(feed):
    request = urllib.request.Request(feed["url"], headers={
        "User-Agent": "CapInvestissementRSS/1.1 (RSS reader)",
        "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml",
    })
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read(5_000_001)
        if len(raw) > 5_000_000:
            raise FeedError("Flux trop volumineux")
        return parse_feed(raw, feed["name"])
    except urllib.error.HTTPError as exc:
        raise FeedError(f"HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError, ET.ParseError) as exc:
        raise FeedError(type(exc).__name__) from None


def load_state():
    if not STATE_PATH.exists():
        return {"version": 2, "feeds": {}, "welcome_sent": False}
    payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if payload.get("version") != 2 or not isinstance(payload.get("feeds"), dict):
        raise ValueError("Format du fichier de suivi invalide")
    return payload


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    for feed_state in state["feeds"].values():
        entries = sorted(feed_state["seen"].items(), key=lambda item: item[1], reverse=True)
        for key, _ in entries[5000:]:
            del feed_state["seen"][key]
    articles = state.get('articles', {})
    for key, _ in sorted(articles.items(), key=lambda entry: entry[1], reverse=True)[20000:]:
        del articles[key]
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    temporary.replace(STATE_PATH)


def webhook_endpoint(value):
    value = value.strip()
    parsed = urllib.parse.urlparse(value)
    if (parsed.scheme != "https" or parsed.hostname not in {"discord.com", "discordapp.com"}
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not re.fullmatch(r"/api/(?:v\d+/)?webhooks/\d+/[A-Za-z0-9_.-]+/?", parsed.path)):
        raise PublishError("Le secret DISCORD_WEBHOOK_URL ne contient pas une URL de webhook Discord valide.")
    # wait=true returns a message ID only after Discord confirms the post.
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "wait=true", ""))


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def discord_post(endpoint, content, files=None):
    payload={"content":content,"username":"CAP · Actualités","avatar_url":"https://raw.githubusercontent.com/parayrealexis66-ship-it/cap-investissement/main/docs/cap-news-avatar.png","allowed_mentions":{"parse":[]}}
    content_type='application/json'
    if files:
        boundary='cap-'+uuid.uuid4().hex
        payload['attachments']=[{'id':i,'filename':name,'description':alt} for i,(name,raw,alt) in enumerate(files)]
        parts=[f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\nContent-Type: application/json\r\n\r\n'.encode()+json.dumps(payload).encode()+b'\r\n']
        for i,(name,raw,alt) in enumerate(files):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="files[{i}]"; filename="{name}"\r\nContent-Type: image/png\r\n\r\n'.encode()+raw+b'\r\n')
        parts.append(f'--{boundary}--\r\n'.encode());body=b''.join(parts)
        content_type=f'multipart/form-data; boundary={boundary}'
    else:
        body=json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(endpoint, data=body, method="POST", headers={
        "Content-Type": content_type, "User-Agent": "CapInvestissementRSS/1.1"})
    opener = urllib.request.build_opener(NoRedirects)
    for attempt in range(3):
        try:
            with opener.open(request, timeout=25) as response:
                result = json.loads(response.read())
            if not isinstance(result, dict) or not result.get("id"):
                raise PublishError("Discord n'a pas confirmé l'envoi du message.")
            return result
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 2:
                try:
                    retry_after = float(json.loads(exc.read()).get("retry_after", 2))
                except (ValueError, TypeError, AttributeError):
                    retry_after = 2
                if 0 <= retry_after <= 30:
                    time.sleep(max(1, retry_after))
                    continue
            raise PublishError(f"Discord a refusé la publication (HTTP {exc.code}).") from None
        except (urllib.error.URLError, OSError, ValueError):
            raise PublishError("Connexion Discord interrompue ; vérifier la prochaine exécution.") from None


def canonical_key(link):
    parsed = urllib.parse.urlsplit(link)
    query = [(k,v) for k,v in urllib.parse.parse_qsl(parsed.query) if not k.lower().startswith('utm_') and k.lower() not in {'fbclid','gclid'}]
    clean = urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip('/'), urllib.parse.urlencode(sorted(query)), ''))
    return hashlib.sha256(clean.encode()).hexdigest()


def matches_filter(feed, item):
    title = item['title'].casefold()
    include = feed.get('include_keywords', [])
    exclude = feed.get('exclude_keywords', [])
    return (not include or any(word.casefold() in title for word in include)) and not any(word.casefold() in title for word in exclude)


def format_message(item):
    published = item["published"].astimezone(PARIS) if item["published"] else None
    date_part = f" · {published:%d/%m/%Y %H:%M} · heure de Paris" if published else ""
    title = re.sub(r"([\\*_~`|])", r"\\\1", item["title"][:600])
    source = re.sub(r"([\\*_~`|])", r"\\\1", item["source"][:120])
    link = item["link"].replace("\n", "").replace("\r", "")
    if len(link) > 900:
        raise PublishError("Lien d'article trop long pour Discord.")
    return f"**{source}**{date_part}\n{title}\n<{link}>"


def publish_entries(feed, entries, state, endpoint, now):
    feed_state = state["feeds"].setdefault(feed["url"], {"initialized": False, "seen": {}})
    seen = feed_state["seen"]
    stamp = now.isoformat()
    cutoff = now - timedelta(hours=FIRST_RUN_LOOKBACK_HOURS)
    if not feed_state["initialized"]:
        # Establish a baseline for each source separately, even if another source was down.
        for item in entries:
            if item["published"] is None or item["published"] < cutoff:
                seen[item["id"]] = stamp
        feed_state["initialized"] = True
        save_state(state)
    pending = [item for item in entries if item["id"] not in seen]
    pending.sort(key=lambda item: item["published"] or now)
    # Shared URL index catches the same article appearing in several feeds.
    article_keys = state.setdefault('articles', {})
    day = now.astimezone(PARIS).date().isoformat()
    daily = state.setdefault('daily', {'date': day, 'count': 0})
    if daily['date'] != day:
        daily.update(date=day, count=0)
    sent = 0
    for item in pending:
        if item["id"] in seen or (item["published"] and item["published"] > now):
            continue
        key = canonical_key(item['link'])
        if key in article_keys or not matches_filter(feed, item) or (item['published'] and item['published'] < now - timedelta(hours=MAX_AGE_HOURS)):
            seen[item['id']] = stamp
            continue
        if sent >= MAX_ITEMS_PER_FEED or daily['count'] >= MAX_DAILY_MESSAGES:
            break
        confirmation = discord_post(endpoint, format_message(item))
        if isinstance(confirmation, dict):
            print(f"Envoi confirmé par Discord : message {confirmation.get('id')} · salon {confirmation.get('channel_id')}.")
        seen[item["id"]] = stamp
        sent += 1
        daily['count'] += 1
        article_keys[key] = stamp
        save_state(state)  # Never mark unsent items; preserve each confirmed post.
    save_state(state)
    print(f"Bilan {feed['name']} : {len(entries)} éléments lus ; {len(pending)} nouveaux identifiants ; {sent} envois confirmés ; quota journalier {daily['count']}/{MAX_DAILY_MESSAGES}.")
    return sent


def write_summary(lines):
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Vérifier les sources sans publier ni modifier le suivi")
    args = parser.parse_args(argv)
    feeds = json.loads(FEEDS_PATH.read_text(encoding="utf-8"))
    if not isinstance(feeds, list) or not feeds:
        raise ValueError("feeds.json doit contenir au moins une source")
    for feed in feeds:
        if (not isinstance(feed, dict) or not feed.get("name")
                or not isinstance(feed.get("url"), str) or not feed["url"].startswith("https://")):
            raise ValueError("Chaque source doit avoir un nom et une URL HTTPS")
    endpoint = None if args.check else webhook_endpoint(os.environ.get("DISCORD_WEBHOOK_URL", ""))
    available, failures = [], []
    for feed in feeds:
        try:
            entries = fetch_feed(feed)
            available.append((feed, entries))
            print(f"Source disponible : {feed['name']} — {len(entries)} éléments.")
        except FeedError as exc:
            failures.append(feed["name"])
            print(f"::warning::Source indisponible : {feed['name']} ({exc}).")
    if not available:
        write_summary(["## Sources indisponibles", "Aucun flux n'a pu être lu ; aucune publication effectuée."])
        return 1
    if args.check:
        write_summary(["## Vérification des sources", f"{len(available)}/{len(feeds)} sources disponibles. Aucun message envoyé."])
        return 1 if failures else 0
    state = load_state()
    if not state.get("welcome_sent"):
        discord_post(endpoint, "✅ **Cap Investissement — flux connecté**\nLa connexion Discord est opérationnelle. Les nouveaux titres seront recherchés deux fois par heure.")
        state["welcome_sent"] = True
        save_state(state)
    from briefing import publish_briefing
    sent = publish_briefing(available, state, endpoint, datetime.now(UTC))
    print(f"Publication terminée : {sent} actualité(s) envoyée(s).")
    write_summary(["## Flux Discord opérationnel", f"{sent} actualité(s) envoyée(s) ; {len(available)}/{len(feeds)} sources disponibles.",
                   f"Plafond : {MAX_DAILY_MESSAGES} actualités/jour (heure de Paris).",
                   "Contrôle prévu deux fois par heure (minutes 15 et 45), sous réserve des délais de GitHub."])
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (PublishError, ValueError, OSError) as exc:
        # Never include an exception traceback or a secret URL in public logs.
        message = str(exc) if isinstance(exc, PublishError) else "Fichier de configuration ou de suivi invalide."
        print(f"::error::{message}", file=sys.stderr)
        write_summary(["## Exécution interrompue", message])
        sys.exit(1)
