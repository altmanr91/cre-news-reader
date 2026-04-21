from rss_fetcher import fetch_articles
from summarizer import get_brief_summary, get_detailed_summary
from article_scraper import get_full_article_text

def run_news_brief():
    print("Fetching articles...\n")
    articles = fetch_articles(max_articles_per_feed=3)
    
    print(f"Found {len(articles)} articles. Summarizing...\n")
    print("=" * 60)
    
    for article in articles:
        print(f"\nSOURCE: {article['source']}")
        print(f"TITLE: {article['title']}")
        print(f"LINK: {article['link']}")
        print(f"PUBLISHED: {article['published']}")
        
        print("\nBRIEF SUMMARY:")
        brief = get_brief_summary(article['title'], article['summary'])
        print(brief)
        
        print("\nFetching full article text...")
        full_text = get_full_article_text(article['link'])
        
        if full_text:
            print("\nDETAILED SUMMARY:")
            detailed = get_detailed_summary(article['title'], full_text)
            print(detailed)
        else:
            print("Full article text unavailable - paywalled or restricted")
        
        print("=" * 60)

if __name__ == "__main__":
    run_news_brief()