from newspaper import Article

def get_full_article_text(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        
        if article.text and len(article.text) > 200:
            return article.text
        else:
            return None
    except Exception as e:
        print(f"Could not fetch full text for {url}: {e}")
        return None

if __name__ == "__main__":
    test_url = "https://commercialobserver.com/2026/03/irvine-co-east-west-bank-pasadena-california-office/"
    
    text = get_full_article_text(test_url)
    
    if text:
        print(f"Successfully fetched full article text")
        print(f"Character count: {len(text)}")
        print(f"\nFirst 500 characters:\n{text[:500]}")
    else:
        print("Could not fetch full article text")