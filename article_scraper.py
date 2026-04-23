import requests
from bs4 import BeautifulSoup
from newspaper import Article

_BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


def _get_bisnow_text(url: str) -> str | None:
    """Bisnow serves full article HTML but requires browser-like headers that newspaper3k doesn't send."""
    try:
        r = requests.get(url, headers=_BROWSER_HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content, 'html.parser')
        container = soup.find(class_='story-container')
        if not container:
            return None
        text = container.get_text(separator=' ', strip=True)
        return text if len(text) > 200 else None
    except Exception as e:
        print(f"Could not fetch Bisnow article {url}: {e}")
        return None


def get_full_article_text(url: str) -> str | None:
    if 'bisnow.com' in url:
        return _get_bisnow_text(url)
    try:
        article = Article(url)
        article.download()
        article.parse()
        if article.text and len(article.text) > 200:
            return article.text
        return None
    except Exception as e:
        print(f"Could not fetch full text for {url}: {e}")
        return None


if __name__ == "__main__":
    tests = [
        ("Bisnow", "https://www.bisnow.com/national/news/data-center-capital-markets/data-centers-grow-150b-blackstone-cites-broader-real-estate-headwinds-134254"),
        ("CO",     "https://commercialobserver.com/2026/03/irvine-co-east-west-bank-pasadena-california-office/"),
    ]
    for name, url in tests:
        text = get_full_article_text(url)
        if text:
            print(f"[{name}] {len(text)} chars — {text[:120]}")
        else:
            print(f"[{name}] FAILED")
