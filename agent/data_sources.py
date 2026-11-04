"""Free data sources: Coinbase spot prices + RSS news headlines."""
import json
import urllib.request
import xml.etree.ElementTree as ET

from . import config

_USER_AGENT = "MorningBriefingRoom/1.0 (FlipTheSwitch hackathon demo)"


def _http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def get_prices(symbols=None):
    """Return {symbol: usd_price} via Coinbase public spot API (no key)."""
    symbols = symbols or config.WATCHLIST
    prices = {}
    for sym in symbols:
        try:
            raw = _http_get(
                f"https://api.coinbase.com/v2/prices/{sym}-USD/spot"
            )
            prices[sym] = float(json.loads(raw)["data"]["amount"])
        except Exception as e:  # one bad symbol must not kill the briefing
            print(f"[prices] {sym}: {type(e).__name__} {e}")
    return prices


def _parse_rss(xml_bytes, source, limit):
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title:
            items.append({"title": title, "link": link, "source": source})
        if len(items) >= limit:
            break
    return items


def get_news(per_feed=None):
    """Return a deduped list of {title, link, source} from free RSS feeds."""
    per_feed = per_feed or config.NEWS_PER_FEED
    seen, out = set(), []
    for source, url in config.NEWS_FEEDS:
        try:
            for item in _parse_rss(_http_get(url), source, per_feed):
                key = item["title"].lower()
                if key not in seen:
                    seen.add(key)
                    out.append(item)
        except Exception as e:
            print(f"[news] {source}: {type(e).__name__} {e}")
    return out
