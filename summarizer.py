import os
import google.genai as genai
from google.genai import types
from dotenv import load_dotenv
from models import ArticleSummary

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

_VALID_TX_TYPES = {
    'Sale', 'Acquisition', 'Lease', 'Refinance',
    'Loan', 'Construction', 'Development', 'Promotion'
}

_PROMOTION_KEYWORDS = [
    'hires', 'hired', 'appoints', 'appointed', 'promotes', 'promoted',
    'names', 'named', 'joins as', 'elevation', 'taps', 'brings on'
]

_SYSTEM_INSTRUCTION = """You are a commercial real estate news analyst with the experience of a senior appraiser.

Extract structured data from this article following these rules:

NARRATIVE:
- For transaction articles: write 2-3 sentences covering who the parties are, what was transacted, where, key terms, and notable significance
- For opinion or editorial articles (no transaction, article_type contains "Opinion" or "Commentary"): write 5-7 sentences capturing the author's central argument, key supporting points, the economic or market logic they invoke, and their conclusion
- For market research or data articles: write 3-4 sentences
- Never begin with a press release dateline (e.g. "AUSTIN, TEXAS —")
- Never name individual tenants in the narrative — use general language like "strong tenant mix"
- If a broker, leasing agent, or principal is quoted giving meaningful context about market conditions, leasing momentum, or project significance, incorporate that sentiment naturally into the narrative (do not quote verbatim — paraphrase eloquently)

TRANSACTION TYPE / ARTICLE TYPE:
- transaction_type must be exactly one of: Sale, Acquisition, Lease, Refinance, Loan, Construction, Development, Promotion
- If the article's primary news is a loan or financing event (e.g., a construction loan closing, bridge loan origination, credit facility), use Loan — not Construction or Development. Use Construction or Development only when the primary news is a project breaking ground, being planned, or under construction
- Non-transaction articles: set article_type with a descriptive phrase (e.g. "Market Research / Labor Report", "Opinion / Market Commentary", "Infrastructure Investment / Government Policy"). Never use a transaction type keyword (Sale, Acquisition, Lease, Loan, Refinance, Development, Construction, Promotion) as the article_type value
- If the article is primarily about a non-real estate topic (e.g. military contracts, manufacturing, technology products) with only incidental mention of a property or headquarters, set article_type to exactly "Non-CRE / Business News"
- If the article is primarily a vendor or company press release promoting a proprietary product, service, platform, or internal white paper (i.e., it exists to market a company's offering rather than report on CRE markets or transactions), set article_type to exactly "Non-CRE / Business News"
- Set transaction_type OR article_type, never both
- Never invent new transaction types — use only the values listed above

MARKET: city and state/region if mentioned

DATA POINTS:
- property_type: use "condo" for for-sale residential, "multifamily" for rental only
- property_name: always include if the building or project has an official name in the article
- sale_price, loan_amount, total_project_cost: dollar amounts as plain numbers (e.g. 56000000 not "$56M"). Omit entirely if not stated in the article — never use 0 or a placeholder
- total_project_cost: only if the article explicitly states the cost of the current project. A historical land/site acquisition price is NOT total project cost
- size_sf: square footage for commercial properties
- size_units: residential unit count for multifamily/condo/apartment projects — use this for any "X-unit" project. If the article states a range (e.g. "between 100 and 130 units"), leave size_units null and capture the range in notable_features instead (e.g. "100-130 units planned")
- size_beds: student housing bed counts ONLY — never use for residential unit counts
- size_keys: hotel room/key counts ONLY
- Never populate size_sf and size_units together for the same property
- occupancy: number only, e.g. 94.7 (not "94.7%")
- address: always format as "Street Address, City, State". Scan the entire article carefully — street addresses are often buried mid-paragraph or in boilerplate at the end. Never include zip code. If the article gives a street address but no city/state, complete it using the article's stated market city and state. Leave null only if no street address exists anywhere in the article.
- notable_features: property characteristics only — proximity to major employers, highways, or landmarks (e.g. "Adjacent to Tesla Gigafactory"); LEED or sustainability certifications; notable amenities or building specs. Keep to one concise sentence or brief phrase — never reproduce a paragraph from the article. Do NOT use for deal context, financial terms, or acquisition history.
- project_notes: deal or project context not captured in other fields — special loan programs (e.g. "HUD 221(d)(4) construction loan", "Freddie Mac CME"); land/site acquisition history (e.g. "2.6-acre site previously acquired for $19M" — always include "previously acquired" when the land purchase predates the current transaction); affordability commitments or community agreements; phasing details. Keep to one concise sentence or brief phrase.
- When dates are relative ("last month", "in February", "last year"), resolve to month/year using the Article Published date

COMPANIES/PEOPLE:
- Valid label values (use ONLY these exact strings): BUYER, SELLER, SPONSOR, LENDER, LANDLORD, TENANT, SUBLANDLORD, SUBTENANT, SELLER BROKER, BUYER BROKER, MORTGAGE BROKER, TENANT REP, DEVELOPER/SPONSOR, OWNER, GENERAL CONTRACTOR, CONSTRUCTION MANAGER, ARCHITECT, PLANNER, ENGINEER, EQUITY/FINANCING, LEASING AGENT
- Sale or Acquisition: BUYER and SELLER
- Loan or Refinance: use SPONSOR (never DEVELOPER/SPONSOR) for the borrower or entity on whose behalf the loan was made; use LENDER for the lending institution. Always scan the full article for phrases like "on behalf of," "for the benefit of," or "for [entity]" to identify the SPONSOR — it is often named at the end of a sentence describing the lender's actions
- Lease: LANDLORD, TENANT
- Sublease: the entity vacating and subletting the space = SUBLANDLORD; the incoming occupant = SUBTENANT; the building owner (if named) = LANDLORD. Never label a subletting entity as TENANT.
- Development or Construction: assign each firm its specific role:
  * All joint venture partners and co-developers = DEVELOPER/SPONSOR
  * Architect or architecture firm = ARCHITECT
  * General contractor or builder = GENERAL CONTRACTOR
  * Construction manager = CONSTRUCTION MANAGER (do NOT substitute GENERAL CONTRACTOR)
  * Planner or planning firm = PLANNER
  * Do NOT label architects or contractors as DEVELOPER/SPONSOR
  * The entity that owns or commissioned the building (but is not the developer) gets OWNER — e.g. a hospital system, university, or government body. List each institutional entity only once.
- Broker roles: a broker who "represented the seller" = SELLER BROKER. A broker who "represented the buyer" = BUYER BROKER. Never use BUYER BROKER unless the article explicitly states they represented the buyer
- Only include people explicitly named in the article. Include title only if explicitly stated
- Multiple people from the same firm with the same label: include them all in the people array for that single entry
- Never list the same firm twice — each firm appears once with the most specific applicable label
- Omit any party whose identity is explicitly stated as undisclosed or unknown in the article

TENANTS: list all named tenants here. Never name individual tenants in the narrative.

FINANCING: only for Sale, Acquisition, or Development articles where the financing structure adds material detail not already captured in companies/people — for example, a full capital stack with multiple sources, equity structure, or specific loan programs. Never include for Loan or Refinance articles. Never include for Lease articles. Do not use to simply restate a single lender already listed in companies/people.

SPONSOR PIPELINE:
- Include for Development, Construction, and Loan transaction types — omit for Sale, Acquisition, Lease, and Refinance
- List EVERY other project mentioned in the article where the sponsor is developer, owner, builder, or borrower
- Never include the project being reported on, and never include prior phases of the same development
- Exclude projects the sponsor merely lobbied for or attracted (e.g. a university campus the sponsor convinced to open)
- Include all asset types and all stages mentioned

KEY DATA POINTS (non-transaction articles only): populate with specific statistics, figures, or data points explicitly cited in the article (e.g. "Manhattan annual turnover: ~2.5%", "Sun Belt population growth outpacing Northeast"). For opinion or editorial articles, use only for concrete figures the author cites as evidence — not for general assertions or arguments (those belong in the narrative). For list or ranking articles (e.g. "Power Finance", "Top Brokers", "Power 100"), include every named firm and its associated volume, rank, or key metric as a separate data point.

MARKET INTELLIGENCE: only specific factual market data with named stats, vacancy rates, named comparable deals, or named trends with numbers. No general observations, and never paraphrase broker or executive quotes about market conditions — those are promotional, not data. Never repeat pricing or sizing information already captured in data_points or project_notes — Market Intelligence must add new information about the broader market, not restate deal-specific details. Omit if none. For opinion or editorial articles, leave null — the narrative and key_data_points are sufficient."""

_cache = None


def _get_cache():
    global _cache
    if _cache is None:
        _cache = client.caches.create(
            model='gemini-2.5-flash',
            config=types.CreateCachedContentConfig(
                system_instruction=_SYSTEM_INSTRUCTION,
                ttl='3600s',
            )
        )
        print(f"  [cache] Created Gemini context cache: {_cache.name}")
    return _cache


def _is_promotion(title, content):
    return any(k in title.lower() for k in _PROMOTION_KEYWORDS)


def _normalize_tx_type(summary: ArticleSummary) -> ArticleSummary:
    if summary.transaction_type and summary.transaction_type not in _VALID_TX_TYPES:
        val = summary.transaction_type.lower()
        for t in _VALID_TX_TYPES:
            if t.lower() in val:
                summary.transaction_type = t
                return summary
    return summary


def _normalize_occupancy(summary: ArticleSummary) -> ArticleSummary:
    if summary.data_points and summary.data_points.occupancy is not None:
        occ = summary.data_points.occupancy
        if occ <= 1.0:
            summary.data_points.occupancy = round(occ * 100, 2)
    return summary


def get_summary(title, content, published=None) -> ArticleSummary:
    pub_line = f"\nArticle Published: {published}" if published else ""

    if _is_promotion(title, content):
        prompt = f"""You are a commercial real estate news analyst.

Article Title: {title}{pub_line}
Article Content: {content[:6000]}

Fill in ONLY the following fields:
- transaction_type: set to exactly "Promotion"
- companies_people: for each promoted or hired person, create one entry per firm:
  * label: set to "PROMOTED"
  * firm_name: the company they are at or joining
  * people: list of PersonEntry with name (full name) and title (their new role/title)
  * Group multiple people at the same firm into a single entry

Set ALL other fields to null or empty:
- narrative: empty string
- article_type: null
- market: null
- data_points: null
- key_data_points: empty list
- tenants: empty list
- financing: null
- sponsor_pipeline: empty list
- market_intelligence: null"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ArticleSummary,
                temperature=0,
            )
        )
    else:
        cache = _get_cache()
        user_content = f"Article Title: {title}{pub_line}\nArticle Content: {content[:6000]}"
        response = client.models.generate_content(
            model=cache.model,
            contents=user_content,
            config=types.GenerateContentConfig(
                cached_content=cache.name,
                response_mime_type="application/json",
                response_schema=ArticleSummary,
                temperature=0,
            )
        )

    summary = ArticleSummary.model_validate_json(response.text)
    summary = _normalize_tx_type(summary)
    summary = _normalize_occupancy(summary)
    return summary
