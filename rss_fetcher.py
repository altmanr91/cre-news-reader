import re
import time
import feedparser
import requests
from datetime import datetime, timezone, timedelta

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# Feeds that block feedparser's HTTP client — pre-fetch with requests instead
_PREFETCH_DOMAINS = {'therealdeal.com'}

# Display name overrides — shown even when the feed returns 0 entries (e.g. TRD CDN blocking)
_FEED_DISPLAY_NAMES = {
    "https://therealdeal.com/national/feed/":      "The Real Deal — National",
    "https://therealdeal.com/new-york/feed/":      "The Real Deal — New York",
    "https://therealdeal.com/miami/feed/":         "The Real Deal — Miami",
    "https://therealdeal.com/chicago/feed/":       "The Real Deal — Chicago",
    "https://therealdeal.com/texas/feed/":         "The Real Deal — Texas",
    "https://therealdeal.com/los-angeles/feed/":   "The Real Deal — Los Angeles",
    "https://therealdeal.com/san-francisco/feed/": "The Real Deal — San Francisco",
    "https://therealdeal.com/washington-dc/feed/": "The Real Deal — Washington DC",
    "https://therealdeal.com/nashville/feed/":     "The Real Deal — Nashville",
    "https://therealdeal.com/las-vegas/feed/":     "The Real Deal — Las Vegas",
    "https://therealdeal.com/atlanta/feed/":       "The Real Deal — Atlanta",
    "https://therealdeal.com/boston/feed/":        "The Real Deal — Boston",
    "https://therealdeal.com/philadelphia/feed/":  "The Real Deal — Philadelphia",
    "https://therealdeal.com/seattle/feed/":       "The Real Deal — Seattle",
    "https://therealdeal.com/denver/feed/":        "The Real Deal — Denver",
}

_STOP_WORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
    'its', 'it', 'as', 'into', 'that', 'this', 'will', 'has', 'have', 'new',
}

def _title_tokens(title: str) -> set:
    words = re.sub(r'[^a-z0-9 ]', '', title.lower()).split()
    return {w for w in words if len(w) > 3 and w not in _STOP_WORDS}

def _is_duplicate(tokens_a: set, tokens_b: set, threshold: float = 0.6) -> bool:
    if not tokens_a or not tokens_b:
        return False
    # Overlap coefficient: how much of the smaller set appears in the larger
    return len(tokens_a & tokens_b) / min(len(tokens_a), len(tokens_b)) >= threshold

def _extract_dollar_millions(text: str) -> set[int]:
    """Extract dollar amounts >= $5M from text, normalized to nearest $1M bucket."""
    results = set()
    for m in re.finditer(r'\$([\d,]+(?:\.\d+)?)\s*(million|billion|[MB])\b', text, re.IGNORECASE):
        try:
            val = float(m.group(1).replace(',', ''))
            unit = m.group(2).lower()
            if unit in ('billion', 'b'):
                val *= 1000  # convert to millions
            if val >= 5:
                results.add(round(val))
        except ValueError:
            pass
    return results

def _deduplicate(articles: list) -> list:
    # Pass 1: exact URL dedup — also excludes URLs seen in the previous run
    seen_urls = {a['url'] for a in PREV_SEEN_ARTICLES}
    unique = []
    for a in articles:
        if a['link'] not in seen_urls:
            seen_urls.add(a['link'])
            unique.append(a)

    # Pass 2: title + summary similarity dedup
    # Seeded with prev-run tokens so cross-day duplicates are caught even after
    # the original article has rolled off its source's RSS feed.
    result = []
    kept_title   = [set(a['title_tokens'])              for a in PREV_SEEN_ARTICLES]
    kept_summary = [set(a.get('summary_tokens', []))    for a in PREV_SEEN_ARTICLES]
    for article in unique:
        t_tok = _title_tokens(article['title'])
        s_tok = _title_tokens(article.get('summary', ''))
        is_dup = False
        for kt, ks in zip(kept_title, kept_summary):
            # Title similarity (original check)
            if _is_duplicate(t_tok, kt):
                is_dup = True
                break
            # Summary similarity — catches same-event articles with dissimilar headlines
            # (e.g. two outlets covering the same earnings report with different titles)
            if ks and s_tok:
                denom = min(len(s_tok), len(ks)) or 1
                if len(s_tok & ks) / denom >= 0.5:
                    t_denom = min(len(t_tok), len(kt)) or 1
                    if len(t_tok & kt) / t_denom >= 0.2:
                        is_dup = True
                        break
        if not is_dup:
            result.append(article)
            kept_title.append(t_tok)
            kept_summary.append(s_tok)

    # Pass 3: dollar-amount fingerprint dedup — catches same-deal coverage from multiple outlets
    # when titles differ enough to beat the overlap threshold (e.g. "$360M Hollywood loan" from CO + TRD)
    result2, kept_prints = [], []
    for article in result:
        combined = article['title'] + ' ' + article.get('summary', '')
        dollars = _extract_dollar_millions(combined)
        tokens  = _title_tokens(article['title'])
        is_dup  = False
        for kept_dollars, kept_tokens_fp in kept_prints:
            shared_dollars = dollars & kept_dollars
            if shared_dollars:
                # Same dollar amount — check for meaningful title token overlap
                overlap = len(tokens & kept_tokens_fp) / min(len(tokens), len(kept_tokens_fp), 1)
                if overlap >= 0.3:
                    is_dup = True
                    break
        if not is_dup:
            result2.append(article)
            kept_prints.append((dollars, tokens))
    return result2

RSS_FEEDS = {
    "Commercial Real Estate": [
        "https://commercialobserver.com/feed/",
        "https://rebusinessonline.com/feed/",
        "https://rejournals.com/feed/",
        "https://therealdeal.com/national/feed/",
        "https://therealdeal.com/new-york/feed/",
        "https://therealdeal.com/miami/feed/",
        "https://therealdeal.com/chicago/feed/",
        "https://therealdeal.com/texas/feed/",
        "https://therealdeal.com/los-angeles/feed/",
        "https://therealdeal.com/san-francisco/feed/",
        "https://therealdeal.com/washington-dc/feed/",
        "https://therealdeal.com/nashville/feed/",
        "https://therealdeal.com/las-vegas/feed/",
        "https://therealdeal.com/atlanta/feed/",
        "https://therealdeal.com/boston/feed/",
        "https://therealdeal.com/philadelphia/feed/",
        "https://therealdeal.com/seattle/feed/",
        "https://therealdeal.com/denver/feed/",
        "https://www.connectcre.com/feed/",
        "https://www.bisnow.com/rss",
    ]
}

# Per-feed article caps — overrides the default max_articles_per_feed
_FEED_CAPS = {
    "https://therealdeal.com/national/feed/": 5,
    "https://therealdeal.com/new-york/feed/": 5,
}

LAST_FEED_STATS = []  # populated on each call to fetch_articles

# Set by digest.py before calling fetch_articles() to enable cross-day dedup.
# Each entry: {"url": str, "title_tokens": list[str], "summary_tokens": list[str]}
PREV_SEEN_ARTICLES: list[dict] = []


def get_seen_articles(articles: list) -> list[dict]:
    """Serialize this run's articles for cross-day dedup on the next run.

    Uses the AI-generated narrative (stored in article['ai_narrative'] by digest.py)
    for summary_tokens when available — promotions have an empty narrative, so they
    won't create false cross-day matches against follow-up articles about the same company.
    """
    return [
        {
            "url": a['link'],
            "title_tokens":   list(_title_tokens(a['title'])),
            "summary_tokens": list(_title_tokens(
                a.get('ai_narrative') or a.get('summary', '')
            )),
        }
        for a in articles
    ]


def _entry_age_hours(entry) -> float | None:
    """Return how many hours ago the entry was published, or None if unknown."""
    pub = entry.get('published_parsed') or entry.get('updated_parsed')
    if not pub:
        return None
    try:
        pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600
    except Exception:
        return None


_AGE_LIMIT_HOURS = 30  # ignore articles older than this (prevents yesterday's digest from repeating)


def fetch_articles(max_articles_per_feed=3):
    global LAST_FEED_STATS
    LAST_FEED_STATS = []
    all_articles = []

    for category, feeds in RSS_FEEDS.items():
        for feed_url in feeds:
            try:
                domain = feed_url.split('/')[2]
                is_slow_domain = any(d in domain for d in _PREFETCH_DOMAINS)
                if is_slow_domain:
                    time.sleep(2)
                feed = feedparser.parse(feed_url, request_headers=HEADERS)
                if len(feed.entries) == 0 and is_slow_domain:
                    raw = requests.get(feed_url, headers=HEADERS, timeout=15).content
                    feed = feedparser.parse(raw)
                source = _FEED_DISPLAY_NAMES.get(feed_url) or feed.feed.get("title") or feed_url
                total_in_feed = len(feed.entries)
                if total_in_feed == 0:
                    print(f"  [warn] Feed returned 0 entries: {source}")
                last_24h = sum(
                    1 for e in feed.entries
                    if (h := _entry_age_hours(e)) is None or h <= 24
                )
                cap = _FEED_CAPS.get(feed_url, max_articles_per_feed)
                fetched = 0
                for entry in feed.entries:
                    if fetched >= cap:
                        break
                    age = _entry_age_hours(entry)
                    if age is not None and age > _AGE_LIMIT_HOURS:
                        continue
                    article = {
                        "category": category,
                        "source": source,
                        "title": entry.get("title", "No title"),
                        "summary": entry.get("summary", ""),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", "Unknown date")
                    }
                    all_articles.append(article)
                    fetched += 1
                LAST_FEED_STATS.append({
                    'source': source,
                    'total_in_feed': total_in_feed,
                    'last_24h': last_24h,
                    'fetched': fetched,
                    'status': getattr(feed, 'status', 200),
                })
            except Exception as e:
                print(f"Error fetching {feed_url}: {e}")
                LAST_FEED_STATS.append({
                    'source': _FEED_DISPLAY_NAMES.get(feed_url, feed_url),
                    'total_in_feed': 0,
                    'last_24h': 0,
                    'fetched': 0,
                    'status': 0,
                    'error': str(e),
                })

    before = len(all_articles)
    all_articles = _deduplicate(all_articles)
    dupes = before - len(all_articles)
    if dupes:
        print(f"  [dedup] Removed {dupes} duplicate article(s)")
    return all_articles

if __name__ == "__main__":
    articles = fetch_articles()
    for article in articles:
        print(f"\nSource: {article['source']}")
        print(f"Title: {article['title']}")
        print("-" * 50)
    print(f"\nTotal articles fetched: {len(articles)}")