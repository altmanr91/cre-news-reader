import feedparser

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

RSS_FEEDS = {
    "Commercial Real Estate": [
        "https://commercialobserver.com/feed/",
        "https://rebusinessonline.com/feed/",
        "https://rejournals.com/feed/",
        "https://therealdeal.com/national/feed/",
        "https://www.connectcre.com/feed/",
        "https://www.bisnow.com/rss",
    ]
}

def fetch_articles(max_articles_per_feed=3):
    all_articles = []

    for category, feeds in RSS_FEEDS.items():
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url, request_headers=HEADERS)
                for entry in feed.entries[:max_articles_per_feed]:
                    article = {
                        "category": category,
                        "source": feed.feed.get("title", feed_url),
                        "title": entry.get("title", "No title"),
                        "summary": entry.get("summary", ""),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", "Unknown date")
                    }
                    all_articles.append(article)
            except Exception as e:
                print(f"Error fetching {feed_url}: {e}")

    return all_articles

if __name__ == "__main__":
    articles = fetch_articles()
    for article in articles:
        print(f"\nSource: {article['source']}")
        print(f"Title: {article['title']}")
        print("-" * 50)
    print(f"\nTotal articles fetched: {len(articles)}")