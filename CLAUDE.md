# CRE News Reader
## Project Overview
A Python-based commercial real estate news aggregation and summarization tool. Fetches articles from RSS feeds, scrapes full article text, and uses OpenAI's API to generate structured brief and detailed summaries with key data points, transaction details, and market intelligence.
## Tech Stack
- **Python 3.13.7**
- **Streamlit** — web interface
- **OpenAI API (gpt-4o-mini)** — AI summarization
- **feedparser** — RSS feed parsing
- **newspaper3k** — full article text scraping
- **python-dotenv** — environment variable management
## Project Structure

News_Reader/ ├── app.py # Main Streamlit web interface ├── summarizer.py # OpenAI prompts for brief and detailed summaries ├── rss_fetcher.py # RSS feed fetching and parsing ├── article_scraper.py # Full article text scraping via newspaper3k ├── main.py # Terminal-based pipeline runner ├── test_env.py # API key verification test ├── .env # API keys (never commit) ├── .gitignore # Excludes .env, venv, pycache ├── requirements.txt # All installed packages └── venv/ # Virtual environment

## Environment Setup
bash
# Activate virtual environment (Windows)
venv\Scripts\activate
# Install dependencies
pip install -r requirements.txt
# Required .env file
OPENAI_API_KEY=sk-...

## Running the App
bash
streamlit run app.py

## RSS Feed Sources
All feeds are dedicated CRE publications:
- Commercial Observer: https://commercialobserver.com/feed/
- RE Business Online: https://rebusinessonline.com/feed/
- RE Journals: https://rejournals.com/feed/
## Key Architecture Decisions
### Article Flow
1. rss_fetcher.py fetches articles from RSS feeds using browser-like headers to avoid blocking
2. article_scraper.py attempts to scrape full article text from each URL
3. summarizer.py sends full text (or RSS preview as fallback) to OpenAI API
4. app.py displays results with clean formatting via Streamlit
### Summary Structure
**Brief Summary** (generated on page load):
- 2-3 sentence overview
- TRANSACTION TYPE (mandatory)
- MARKET
- KEY DATA POINTS (transaction amount, size, $/SF or $/unit, occupancy, etc.)
**Detailed Summary** (generated on click):
- KEY DETAILS (property specifics)
- TRANSACTION TYPE
- DATA POINTS (full metrics including $/SF stated vs calculated)
- MARKET CONTEXT
- COMPANIES/PEOPLE (labeled by transaction type: BUYER/SELLER, SPONSOR/LENDER, LANDLORD/TENANT)
- PARTY PROFILES
- MARKET INTELLIGENCE
- NOTABLE QUOTES
### Companies/People Labeling
Labels are assigned based on transaction type:
- Sale/Acquisition: BUYER and SELLER
- Loan/Refinance: SPONSOR and LENDER
- Lease: LANDLORD and TENANT
- Development/Construction: SPONSOR
- Additional: SELLER BROKER, BUYER BROKER, MORTGAGE BROKER, TENANT REP, etc.
### Text Cleaning (clean_text in app.py)
- Replaces backticks and Unicode lookalikes with $ signs
- Strips placeholder text (Not mentioned, N/A, etc.)
- Fixes malformed dollar ranges
- Removes empty section headers
### Transaction Type Detection (ensure_transaction_type in app.py)
Programmatic fallback that detects transaction type from title and content keywords if the AI omits it.
## Known Issues / Future Work
### Sources to Add (require advanced scraping)
- Bisnow — removed, blocked automated access
- CoStar News — requires paid subscription + API
- Connect CRE — blocked, 403 errors
- GlobeSt — FeedBlitz blocks automated requests
- The Real Deal — rate limits automated access
### Planned Features
- Fix full text scraping for blocked sources (Bisnow, CoStar, Connect CRE, GlobeSt)
- Add The Real Deal back with rate limiting
- Expand character limit beyond 3,000 for detailed summaries
- Search/filter by keyword, topic, market, transaction type
- Deal size filter (minimum dollar amount)
- Geography filter by market/city
- Date range for historical articles
- Relevance ranking system
- Daily email digest automation
- Contact info/leads list from deal participants
- Deal enrichment — scrape additional sources for more data
- Multiple user support
- Deployment to cloud server
- Upgrade to gpt-4o for better accuracy
- $/SF discrepancy handling improvements
- Notable Quotes prompt refinement
- Companies/People extraction improvements
## Model Notes
- Currently using gpt-4o-mini for both brief and detailed summaries
- gpt-3.5-turbo was used initially but had issues with complex prompt following
- Plan to upgrade to gpt-4o when scaling up for better arithmetic and instruction following
- Token limits: 400 for brief, 1500 for detailed
- Article text capped at 3,000 characters per API call
## Caching
- @st.cache_data(ttl=0) — currently set to no caching for development
- Change to ttl=1800 (30 minutes) for production use
## Cost Notes
- gpt-4o-mini: ~$0.003 per article summary
- At 6 articles per run: ~$0.018 per refresh
- At 2 refreshes/day: ~$0.54/month

