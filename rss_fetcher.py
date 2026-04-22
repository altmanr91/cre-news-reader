import re
import time
import feedparser
from datetime import datetime, timezone, timedelta

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

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

def _deduplicate(articles: list) -> list:
    # Pass 1: exact URL dedup
    seen_urls, unique = set(), []
    for a in articles:
        if a['link'] not in seen_urls:
            seen_urls.add(a['link'])
            unique.append(a)

    # Pass 2: title similarity dedup (keep first occurrence per story)
    result, kept_tokens = [], []
    for article in unique:
        tokens = _title_tokens(article['title'])
        if not any(_is_duplicate(tokens, kt) for kt in kept_tokens):
            result.append(article)
            kept_tokens.append(tokens)
    return result

RSS_FEEDS = {
    "Commercial Real Estate": [
        "https://commercialobserver.com/feed/",
        "https://rebusinessonline.com/feed/",
        "https://rejournals.com/feed/",
        "https://therealdeal.com/national/feed/",
        "https://www.connectcre.com/feed/",
        "https://www.bisnow.com/rss",
        "https://shoppingcenterbusiness.com/feed/",
    ]
}

LAST_FEED_STATS = []  # populated on each call to fetch_articles


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


def fetch_articles(max_articles_per_feed=3):
    global LAST_FEED_STATS
    LAST_FEED_STATS = []
    all_articles = []

    for category, feeds in RSS_FEEDS.items():
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url, request_headers=HEADERS)
                source = feed.feed.get("title", feed_url)
                total_in_feed = len(feed.entries)
                last_24h = sum(
                    1 for e in feed.entries
                    if (h := _entry_age_hours(e)) is None or h <= 24
                )
                LAST_FEED_STATS.append({
                    'source': source,
                    'total_in_feed': total_in_feed,
                    'last_24h': last_24h,
                    'fetched': min(max_articles_per_feed, total_in_feed),
                    'status': getattr(feed, 'status', 200),
                })
                for entry in feed.entries[:max_articles_per_feed]:
                    article = {
                        "category": category,
                        "source": source,
                        "title": entry.get("title", "No title"),
                        "summary": entry.get("summary", ""),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", "Unknown date")
                    }
                    all_articles.append(article)
            except Exception as e:
                print(f"Error fetching {feed_url}: {e}")
                LAST_FEED_STATS.append({
                    'source': feed_url,
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