# CRE News Reader — App 1 (Daily Digest)

## Project Overview
A Python-based commercial real estate news aggregation and summarization tool. Fetches articles from RSS feeds, scrapes full article text, and uses Google's Gemini API to generate structured summaries with narratives, key data points, transaction details, companies/people, and market intelligence. Delivered as a daily HTML email digest with linked detail pages hosted on GitHub Pages.

## Tech Stack
- **Python 3.12** (GitHub Actions) / **3.13.7** (local)
- **Google Gemini 2.5 Flash** — AI summarization with context caching
- **feedparser + requests** — RSS feed fetching (requests fallback for feeds that block feedparser)
- **newspaper3k** — full article text scraping
- **python-dotenv** — environment variable management
- **smtplib / Gmail SMTP** — email delivery
- **GitHub Pages** — static hosting for digest HTML and per-article detail pages

## Project Structure
```
News_Reader LIVE/
├── digest.py          # Main pipeline: fetch → summarize → build HTML → email → deploy
├── summarizer.py      # Gemini API calls, context caching, structured extraction
├── rss_fetcher.py     # RSS fetching with per-feed caps, TRD rate-limit handling, dedup
├── article_scraper.py # Full article text scraping via newspaper3k
├── filter.py          # Pre- and post-summary filtering logic
├── models.py          # Pydantic models: ArticleSummary, DataPoints, CompanyEntry, etc.
├── geocoder.py        # Property address lookup via Serper + Google Maps APIs
├── calculator.py      # Derived metrics: $/SF, $/unit, Loan/SF calculated from data_points
├── server.py          # Local HTTP server (port 8787) for testing detail pages locally
├── app.py             # Legacy Streamlit web interface (not used in production)
├── main.py            # Legacy terminal pipeline runner (not used in production)
├── run_digest.bat     # Local batch file wrapper (for manual runs only)
├── .github/workflows/
│   └── daily_digest.yml  # GitHub Actions: runs at 5 AM EDT, deploys to GitHub Pages
├── .env               # API keys (never commit)
├── .gitignore
└── requirements.txt
```

## Environment Variables
```
GEMINI_API_KEY=...          # Google Gemini API
GMAIL_APP_PASSWORD=...      # Gmail app password for SMTP sending
DIGEST_BASE_URL=...         # Set by GitHub Actions to GitHub Pages URL; localhost:8787 locally
SERPER_API_KEY=...          # Optional: Serper web search for property address geocoding
GOOGLE_MAPS_API_KEY=...     # Optional: Google Maps validation for geocoded addresses
```

## Scheduling & Delivery
- **GitHub Actions** runs the digest daily at 5:00 AM EDT (`cron: '0 9 * * *'` UTC)
- GitHub Actions queue delays mean email typically arrives between 7:00–8:00 AM EDT
- Email sent via Gmail SMTP to `altmanr91@gmail.com`
- HTML digest and per-article pages deployed to **GitHub Pages** after each run
- GitHub Pages site: `https://altmanr91.github.io/CRE-News-Reader`
- Windows Task Scheduler task ("CRE Daily Digest") exists locally but is **disabled** — GitHub Actions is authoritative

## RSS Feed Sources
All feeds are CRE publications. Per-feed article caps override the default (5 per feed):

| Source | URL | Cap |
|---|---|---|
| Commercial Observer | commercialobserver.com/feed/ | 5 (default) |
| RE Business Online | rebusinessonline.com/feed/ | 5 (default) |
| RE Journals | rejournals.com/feed/ | 5 (default) |
| The Real Deal — National | therealdeal.com/national/feed/ | **5** |
| The Real Deal — New York | therealdeal.com/new-york/feed/ | **5** |
| The Real Deal — Miami | therealdeal.com/miami/feed/ | 3 |
| The Real Deal — Chicago | therealdeal.com/chicago/feed/ | 3 |
| The Real Deal — Texas | therealdeal.com/texas/feed/ | 3 |
| The Real Deal — Los Angeles | therealdeal.com/los-angeles/feed/ | 3 |
| The Real Deal — San Francisco | therealdeal.com/san-francisco/feed/ | 3 |
| The Real Deal — Washington DC | therealdeal.com/washington-dc/feed/ | 3 |
| The Real Deal — Nashville | therealdeal.com/nashville/feed/ | 3 |
| The Real Deal — Las Vegas | therealdeal.com/las-vegas/feed/ | 3 |
| The Real Deal — Atlanta | therealdeal.com/atlanta/feed/ | 3 |
| The Real Deal — Boston | therealdeal.com/boston/feed/ | 3 |
| The Real Deal — Philadelphia | therealdeal.com/philadelphia/feed/ | 3 |
| The Real Deal — Seattle | therealdeal.com/seattle/feed/ | 3 |
| The Real Deal — Denver | therealdeal.com/denver/feed/ | 3 |
| Connect CRE | connectcre.com/feed/ | 5 (default) |
| Bisnow | bisnow.com/rss | 5 (default) |

**TRD note:** TRD blocks feedparser's HTTP client for some regional feeds. rss_fetcher.py adds a 2s delay between TRD requests and falls back to the `requests` library if feedparser returns 0 entries. Rate limiting is per-IP and only a concern during repeated local testing — GitHub Actions uses a fresh IP each run.

**Removed:** Shopping Center Business (duplicated RE Business Online content).

## Pipeline Flow (digest.py)
1. `rss_fetcher.fetch_articles()` — fetch all feeds, deduplicate by URL then title similarity
2. `filter.get_title_filter_reason()` — title-level pre-filter (no API cost)
3. `article_scraper.get_full_article_text()` — scrape full text via newspaper3k
4. `summarizer.get_summary()` — Gemini API call with 6,000-char article content cap
5. `geocoder.inject_geocoded_address()` — look up street address if not in article
6. `filter.get_summary_filter_reason()` — post-summary filter on article_type/transaction_type
7. `digest.build_browser_html()` — full browser digest with collapsible sections, feed stats
8. `digest.build_email_html()` — narrative-only email with Details links to GitHub Pages
9. Per-article HTML pages saved and deployed to GitHub Pages via `peaceiris/actions-gh-pages`
10. Email sent via Gmail SMTP

## Filtering Logic (filter.py)
Filtering runs at two points to minimize unnecessary API calls.

**Title-level pre-filters** (before API call):
- `_TITLE_AWARD_PATTERNS` — TOBY awards, deal of the year, building awards → "Property/Deal Award"
- `_TITLE_EVENT_PATTERNS` — conferences, webinars, expos, symposiums → "Industry Event"
- `_TITLE_ASSOCIATION_PATTERNS` — BOMA/NAIOP/NAR announcements → "Association News"
- `_TITLE_NONCRE_PATTERNS` — "National X Week" celebrations, city youth/school investment → "Non-CRE Content"

**Post-summary filters** (after API call, using model's classification):
- `article_type` contains "non-cre" → "Non-CRE Content"
- `article_type` contains "award" → "Property/Deal Award"
- `article_type` contains "association/membership/organization" → "Association News"
- `article_type` contains "event/conference/expo/webinar" → "Industry Event"
- Promotions: always kept regardless of seniority level, displayed compactly (name/title/company/link only). Excluded at the model prompt level: people at proptech/tech/service companies (not CRE principals), non-CRE support roles (HR, IT, marketing, legal), brokerage engagement/listing appointments (not personal hires)

Filtered articles appear in a collapsed "FILTERED (N)" section at the bottom of the browser digest. They do not appear in the email.

## AI Summarization (summarizer.py)
- **Model:** `gemini-2.5-flash`
- **Context caching:** System instruction cached for 1 hour (TTL=3600s) — avoids re-sending the large prompt on every article
- **Thinking mode:** disabled (`thinking_budget=0`) to eliminate hidden token costs
- **Article content cap:** 6,000 characters
- **Temperature:** 0 (deterministic)
- **Structured output:** Gemini JSON mode with `response_schema=ArticleSummary`
- Promotions use a simplified prompt (no cache) since they only need name/title/company

## Data Model (models.py)
Key fields extracted per article:
- `narrative` — 2–4 sentence summary
- `transaction_type` — Sale, Acquisition, Lease, Loan, Refinance, Development, Construction, Promotion
- `article_type` — for non-transaction articles (e.g. "Market Research / Office Trends")
- `market` — city and state
- `data_points` — DataPoints object: property_type, address, size_sf, size_units, size_beds, size_keys, sale_price, loan_amount, total_project_cost, occupancy, year_built, completion, notable_features, project_notes
- `companies_people` — list of CompanyEntry with label (BUYER/SELLER/SPONSOR/LENDER/etc.), firm_name, people
- `tenants` — list of named tenants (kept separate from narrative)
- `financing` — capital stack detail for Sale/Development articles
- `sponsor_pipeline` — other projects by the same sponsor
- `market_intelligence` — specific market stats with named figures
- `key_data_points` — for market/research articles

## Calculated Metrics (calculator.py)
`inject_calculated_metrics()` computes $/SF, $/unit, $/bed, $/key, Loan/SF from typed numbers.
Suppressed when:
- No price or no size fields present
- REIT/corporate acquisitions priced per share (model leaves `size_sf` null per prompt instruction)
- Mixed-use with large SF (ambiguous which component the price applies to)

## Geocoding (geocoder.py)
When an article has a property name but no street address:
1. Serper API searches Google for `"[property_name]" [market] address`
2. Regex extracts street address from search results
3. Google Maps API validates and formats the address
4. Address flagged with `address_sourced_separately=True` and shown with `*` in digest
- Requires `SERPER_API_KEY` and `GOOGLE_MAPS_API_KEY` in `.env` / GitHub Secrets

## Digest Output Structure
**Email** (narrative-only, sent via Gmail):
- Grouped by: transaction type → region → market
- Regions: National/Multi-Market, Northeast, Mid-Atlantic, Southeast, Midwest, Texas, Mountain West, West Coast
- Shows: article title (linked), source, date, narrative, "Details →" link to GitHub Pages

**Browser digest** (full detail, hosted on GitHub Pages):
- Same grouping as email
- Per-article collapsible sections: SUMMARY, DATA POINTS, COMPANIES/PEOPLE, TENANTS, FINANCING, SPONSOR PIPELINE, MARKET INTELLIGENCE
- Bottom: FILTERED (N) — collapsed list of filtered articles with reasons
- Bottom: SOURCE VOLUME — per-feed stats (last 24h articles, total in feed, fetched count)

**Per-article detail pages** (GitHub Pages `/articles/YYYY-MM-DD-NNN.html`):
- All sections expanded
- "← Full Digest" back link

## Cost Notes (Gemini 2.5 Flash)
- Context cache creation: ~$0.002 (one-time per run, cached 1 hour)
- Per article with cache hit: ~$0.001–0.003
- Full run (~35 articles): ~$0.05–0.10
- Monthly (30 runs): ~$1.50–3.00

## Known Limitations / Future Work

### Source Scraping
- **Bisnow** — RSS works, full-text scraping blocked. Summaries based on RSS preview only (weaker quality)
- **Connect CRE** — RSS works, full-text scraping may be limited
- **CoStar News** — requires paid subscription + API, not integrated
- **GlobeSt** — FeedBlitz blocks automated requests, not integrated
- **TRD regional feeds** — some may return 0 entries depending on TRD's CDN behavior; all errors caught gracefully

### App 1 Planned Improvements
- Improve full-text scraping for Bisnow and Connect CRE
- Deal size filter (minimum dollar amount)
- Keyword/market/transaction-type search and filter
- Smarter filtering for residential TRD articles (TRD regional feeds mix residential and CRE)
- Refine deduplication threshold (currently 0.6 overlap coefficient)
- Notable Quotes extraction improvements
- Add more CRE sources (GlobeSt, CoStar if access obtained)

### App 2 — Comprehensive CRE Feed (Planned)
Goal: 100% coverage of all CRE articles within a 24-hour window, no duplicates, no irrelevant content. Intended as a separate application from this digest.
- Requires near-real-time fetching (not once-daily)
- Stronger deduplication across all sources
- Smarter relevance filtering before summarization
- Persistent article database (not ephemeral per-run)
- Prerequisites: dedup and filtering logic proven in App 1 first

### App 3 (Concept)
- Not yet defined — likely a searchable database or deal-tracking layer built on top of App 2's data

## Local Development
```bash
# Activate virtual environment (Windows)
venv\Scripts\activate

# Run digest manually (saves HTML locally, sends email, restarts local server)
python digest.py

# Start local server only (serves existing HTML files at localhost:8787)
venv\Scripts\pythonw.exe server.py

# Test RSS fetching
python rss_fetcher.py

# Required .env file
GEMINI_API_KEY=...
GMAIL_APP_PASSWORD=...
SERPER_API_KEY=...          # optional
GOOGLE_MAPS_API_KEY=...     # optional
```

## GitHub Actions Workflow
File: `.github/workflows/daily_digest.yml`
- Runs on `ubuntu-latest`
- Installs: `google-genai feedparser python-dotenv pydantic requests lxml[html_clean] beautifulsoup4 newspaper3k`
- Secrets required: `GEMINI_API_KEY`, `GMAIL_APP_PASSWORD`, `SERPER_API_KEY`, `GOOGLE_MAPS_API_KEY`
- `DIGEST_BASE_URL` set to `https://altmanr91.github.io/CRE-News-Reader`
- After digest runs: copies HTML to `_site/`, deploys to GitHub Pages via `peaceiris/actions-gh-pages`
- Server restart is skipped in CI (`if not os.getenv('CI')`)
