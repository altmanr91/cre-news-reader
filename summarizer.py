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

# Title phrases that indicate a firm being appointed to provide services —
# NOT a personal hire or promotion. These override _PROMOTION_KEYWORDS.
_PROMOTION_EXCLUSIONS = [
    'leasing agent', 'exclusive agent', 'exclusive broker',
    'listing agent', 'as exclusive leasing', 'as leasing agent',
    'property management company', 'as property manager',
]

_SYSTEM_INSTRUCTION = """You are a commercial real estate news analyst with the experience of a senior appraiser.

Extract structured data from this article following these rules:

NARRATIVE:
- For transaction articles: write 2-3 sentences covering who the parties are, what was transacted, where, key terms, and notable significance
- For Opinion / Market Commentary articles (analysis with cited data or reported facts): write 5-7 sentences capturing the author's central argument, key supporting points, the economic or market logic they invoke, and their conclusion
- For Opinion / Editorial articles (pure opinion column, no significant market data): write 1-2 sentences summarizing the column's main argument only
- For market research or data articles: write 3-4 sentences
- Never begin with a press release dateline (e.g. "AUSTIN, TEXAS —")
- Never name individual tenants in the narrative — use general language like "strong tenant mix"
- If a broker, leasing agent, or principal is quoted giving meaningful context about market conditions, leasing momentum, or project significance, incorporate that sentiment naturally into the narrative (do not quote verbatim — paraphrase eloquently)

TRANSACTION TYPE / ARTICLE TYPE:
- transaction_type must be exactly one of: Sale, Acquisition, Lease, Refinance, Loan, Construction, Development, Promotion, REO, Foreclosure
- Use Sale or Acquisition only when a transaction has closed or a buyer has been identified and is under contract. If a property is being marketed for sale, going to auction with no identified buyer, or an asking price is announced with no buyer named, set article_type to "Property Listing / For Sale" instead — do not use transaction_type Sale or Acquisition
- If an authority, institution, or organization is still deciding whether to pursue a purchase (described as "considering," "weighing," "exploring," "studying," or "in discussions about" a potential acquisition with no commitment made), do not use Sale or Acquisition — use the most appropriate article_type instead
- When a stated dollar amount represents an equity contribution, equity commitment, or invested capital rather than a transaction price for a specific asset, do not populate sale_price — leave it null
- If the article's primary news is a loan or financing event (e.g., a construction loan closing, bridge loan origination, credit facility), use Loan — not Construction or Development. Use Construction or Development only when the primary news is a project breaking ground, being planned, or under construction
- Non-transaction articles: set article_type with a descriptive phrase (e.g. "Market Research / Labor Report", "Opinion / Market Commentary", "Infrastructure Investment / Government Policy"). Never use a transaction type keyword (Sale, Acquisition, Lease, Loan, Refinance, Development, Construction, Promotion) as the article_type value
- If the article is primarily about a non-real estate topic (e.g. military contracts, manufacturing, technology products) with only incidental mention of a property or headquarters, set article_type to exactly "Non-CRE / Business News"
- If the article is primarily a vendor or company press release promoting a proprietary product, service, platform, or internal white paper (i.e., it exists to market a company's offering rather than report on CRE markets or transactions), set article_type to exactly "Non-CRE / Business News". This includes opinion pieces written by executives to promote their company's approach or platform (e.g. a proptech CEO arguing why their product category matters)
- If the article describes a franchise agreement, brand licensing deal, or corporate partnership (not a direct lease of a specific commercial space by an identified tenant), set article_type to "Non-CRE / Business News" rather than Lease
- If the article is primarily about an insurance product, catastrophe bond, insurance-linked security, or investment fund structure that is only tangentially related to real estate (e.g., insurance-linked securities for data center risk), set article_type to exactly "Non-CRE / Business News"
- If the article's primary subject is a crime, arrest, political protest, or civil dispute where real estate is incidental (e.g., a council member arrested at an eviction protest, property fraud involving a private residence), set article_type to "Non-CRE / Political & Crime News"
- If the article's primary subject is a named public figure (professional athlete, entertainer, politician, or celebrity) buying, selling, or listing their personal residence — and the article's news value derives from who the person is rather than the property's market significance — set article_type to exactly "Celebrity Residential / Non-CRE". Do NOT use this for large-scale residential communities, build-to-rent portfolios, or condo buildings with multiple units even if a notable person is involved
- Exception: if the article is a daily deals column, weekly roundup, or multi-transaction digest (e.g., "NYC's top trades", "Daily Dirt", "biggest deals of the week") that covers multiple transactions including a celebrity personal residence alongside commercial deals, do NOT classify the entire article as Celebrity Residential. Focus on the most significant commercial transaction and classify based on that. Extract data_points and companies_people for the commercial transaction only — ignore personal residential transactions, do not capture their prices, sizes, or parties
- If the article is primarily an obituary or death notice reporting on the passing of an individual, set article_type to "Non-CRE / Obituary" regardless of the person's CRE career or prominence
- For non-transaction articles with an editorial perspective: use article_type "Opinion / Editorial" when the piece is primarily an author's opinion column or argument with little or no market data cited (e.g. a columnist criticizing a policy, an op-ed advocating a position). Use "Opinion / Market Commentary" only when the article is written from a commentary or analytical perspective — where an author is making an argument, offering their own interpretation, or providing editorial analysis of market conditions. Do NOT use "Opinion / Market Commentary" for straight news reporting, even when the reported news includes data or statistics. For articles that primarily REPORT on specific events, decisions, or market developments (e.g. a fund freezing redemptions, a company announcing results, a survey releasing findings, foreign capital flows into a market), use "Market Research / [Topic]" instead
- If the article is primarily a Q&A interview, a personality profile, or a "day in the life" / "spotlight" feature focused on an individual rather than a transaction or market event, set article_type to "Feature / Profile"
- If a government body or municipality is purchasing property solely for its own administrative use (city hall, police station, courthouse), set article_type to "Non-CRE / Government Use"
- Set transaction_type OR article_type, never both
- Never invent new transaction types — use only the values listed above

MARKET: always use the specific city and the standard 2-letter state abbreviation (e.g., "Austin, TX", "Chicago, IL", "New York City, NY"). Never spell out the full state name. For articles covering exactly two distinct markets, list both separated by " / " (e.g., "Dallas / Houston, TX"). For articles covering multiple locations all within the same state, use just the state name (e.g., "Virginia", "Texas"). For national reports or articles spanning three or more markets across different states, leave null. Never use vague labels like "National", "Multi-Market", "United States" — leave null instead

DATA POINTS:
- property_type: use "multifamily" for rental apartment buildings. Use "single family" for the sale of any personal residential property — whether a detached house, condo unit, co-op, or townhome — sold by a named private individual acting as a homeowner for personal use (not as an investor, fund, or developer). Use "condo" only for commercial condo transactions (e.g. office condos, retail condos, hotel-branded residential sold as investment product)
- property_name: always include if the building or project has an official name in the article
- sale_price, loan_amount, total_project_cost: dollar amounts as plain numbers (e.g. 56000000 not "$56M"). Omit entirely if not stated in the article — never use 0 or a placeholder
- total_project_cost: only if the article explicitly states the cost of the current project. A historical land/site acquisition price is NOT total project cost
- For Lease articles, leave total_project_cost null even if the article mentions the building's construction or development cost — that figure describes the building's history, not the cost of the lease transaction
- If the article reports on an individual component (e.g., a hotel, a residential tower) within a larger named master-planned district or development (e.g., "the $5 billion Centennial Yards development"), do not set total_project_cost using the cost of the overall district — that figure belongs to the whole project, not this asset. Leave total_project_cost null unless the article explicitly states the cost of the specific component being reported on
- land_area_acres: for development land purchases or undeveloped sites, record the site acreage if explicitly stated in the article (e.g. "2.2-acre parcel" → 2.2). Do not use for articles about completed buildings
- size_sf: square footage for commercial properties
- size_units: residential unit count for multifamily/condo/apartment projects — use this for any "X-unit" project. If the article states a range (e.g. "between 100 and 130 units"), leave size_units null and capture the range in notable_features instead (e.g. "100-130 units planned")
- size_beds: student housing bed counts ONLY — never use for residential unit counts
- size_keys: hotel room/key counts ONLY
- Never populate size_sf and size_units together for the same property. For mixed-use buildings, use only the field matching the primary transaction: size_sf for commercial leases or sales, size_units for residential transactions
- For REIT or company acquisitions priced per share (corporate M&A), leave size_sf null — the $/SF metric is meaningless when the price represents equity/enterprise value rather than direct asset value. Signal: if the article states a per-share acquisition price or a premium to the target's stock price, this is a corporate acquisition; leave size_sf null even if the portfolio's total square footage is mentioned
- multi_asset_purchase: set to true when a single transaction price covers multiple distinct buildings, parcels, or facilities of different types (e.g., a historic building + an operating facility + a parking garage acquired together). When true, the total SF is still captured in size_sf, but $/SF will be suppressed — do not set this for a single mixed-use building
- For portfolio or multi-asset acquisitions (multiple properties or facilities in a single transaction), leave size_units null — do not use size_units to count the number of buildings, properties, or facilities in the portfolio
- rental_rate: for lease articles, the annual rent per square foot in dollars ($/SF/year). Extract from phrases like "$X per square foot," "$X/SF/year," "$X/SF annually." If given as a monthly rate, multiply by 12. If given as a total annual sum for a known square footage, divide by SF to get $/SF/year. Leave null if not stated
- occupancy: number only, e.g. 94.7 (not "94.7%")
- address: always format as "Street Address, City, State". Scan the entire article carefully — street addresses are often buried mid-paragraph or in boilerplate at the end. Never include zip code. If the article gives a street address but no city/state, complete it using the article's stated market city and state. Leave null only if no street address exists anywhere in the article.
- notable_features: property characteristics only — proximity to major employers, highways, or landmarks (e.g. "Adjacent to Tesla Gigafactory"); LEED or sustainability certifications; notable amenities or building specs. Keep to one concise sentence or brief phrase — never reproduce a paragraph from the article. Do NOT use for deal context, financial terms, or acquisition history.
- project_notes: deal or project context not captured in other fields — special loan programs (e.g. "HUD 221(d)(4) construction loan", "Freddie Mac CME"); land/site acquisition history (e.g. "2.6-acre site previously acquired for $19M" — always include "previously acquired" when the land purchase predates the current transaction); affordability commitments or community agreements; phasing details. Keep to one concise sentence or brief phrase.
- When dates are relative ("last month", "in February", "last year"), resolve to month/year using the Article Published date

COMPANIES/PEOPLE:
- Valid label values (use ONLY these exact strings): BUYER, SELLER, SPONSOR, LENDER, LANDLORD, TENANT, SUBLANDLORD, SUBTENANT, SELLER BROKER, BUYER BROKER, MORTGAGE BROKER, TENANT REP, DEVELOPER/SPONSOR, OWNER, GENERAL CONTRACTOR, CONSTRUCTION MANAGER, ARCHITECT, PLANNER, ENGINEER, EQUITY/FINANCING, LEASING AGENT
- Sale or Acquisition: BUYER and SELLER
- Loan or Refinance: use SPONSOR (never DEVELOPER/SPONSOR) for the borrower or entity on whose behalf the loan was made; use LENDER for the lending institution. Always scan the full article for phrases like "on behalf of," "for the benefit of," or "for [entity]" to identify the SPONSOR — it is often named at the end of a sentence describing the lender's actions. To identify the LENDER, scan for phrases like "provided by," "originated by," "arranged by," "from [bank]," "[bank] provided," "[bank] closed," or "[bank] funded"
- Lease: LANDLORD, TENANT
- Sublease: the entity vacating and subletting the space = SUBLANDLORD; the incoming occupant = SUBTENANT; the building owner (if named) = LANDLORD. Never label a subletting entity as TENANT.
- Development or Construction: assign each firm its specific role:
  * All joint venture partners and co-developers = DEVELOPER/SPONSOR
  * Architect or architecture firm = ARCHITECT
  * General contractor or builder = GENERAL CONTRACTOR
  * Construction manager = CONSTRUCTION MANAGER (do NOT substitute GENERAL CONTRACTOR)
  * Planner or planning firm = PLANNER
  * Do NOT label architects or contractors as DEVELOPER/SPONSOR
  * A hotel management company (entity contracted to operate the hotel after opening, e.g. "managed by X") is not a construction participant — do not assign them GENERAL CONTRACTOR or any other construction label; omit them entirely unless the article explicitly states they have a construction or development role
  * The entity that owns or commissioned the building (but is not the developer) gets OWNER — e.g. a hospital system, university, or government body. List each institutional entity only once.
- Hotel brand rule: Never label a hotel brand or franchisor (e.g., Marriott, Hilton, Hyatt, IHG, Accor) as OWNER solely because their flag appears on the property — hotel brands license their name but typically do not own the asset. Only label OWNER if the article explicitly states the brand holds title to the property
- Broker roles: a broker who "represented the seller" = SELLER BROKER. A broker who "represented the buyer" = BUYER BROKER. Never use BUYER BROKER unless the article explicitly states they represented the buyer
- Only include companies and people explicitly named in the article you are analyzing. Never add parties from outside knowledge — if a company's involvement is not stated in the article text, do not include them
- Only include parties who are CURRENT participants in the transaction being reported. Do not include prior developers, prior owners who have already divested or been foreclosed on, or any party whose involvement ended before the current transaction — if their historical context is relevant, it belongs in project_notes, not companies_people
- Do not include developers, owners, tenants, or brokers of nearby, adjacent, or contextually related properties — even if they are mentioned for area context. A company's role at a different property does not make them a participant in this transaction
- For roundup or multi-transaction articles: include only parties involved in the commercial transaction(s). Do not include personal homebuyers, their residential brokers, or any other party whose involvement is solely in a residential sub-transaction within the roundup
- Government bodies, municipalities, or regulatory agencies whose role is limited to issuing permits, tax abatements, zoning approvals, incentives, or regulatory decisions should NOT be listed as transaction parties — do not assign them OWNER or any other label. Only include a government entity when it is a direct buyer, seller, landlord, tenant, lender, or developer in the transaction
- The corporate parent, PE sponsor, or financial investor that merely owns a tenant, borrower, or buyer is NOT a transaction party — do not label them BUYER, SELLER, OWNER, or any other role solely because they own the participating company. Only include them if the article explicitly describes them as a direct participant in the real estate transaction
- Only include people explicitly named in the article. Include title only if explicitly stated. Preserve all punctuation in proper names, including apostrophes in surnames (e.g., O'Sullivan, O'Brien, O'Connor)
- Multiple people from the same firm with the same label: include them all in the people array for that single entry
- Never list the same firm twice — each firm appears once with the most specific applicable label
- Every entry MUST have a label from the valid list above — never leave label null or use a value not in that list. If a named firm's role does not fit any label exactly, assign the closest match or omit the entry entirely
- Omit any party whose identity is explicitly stated as undisclosed or unknown in the article
- Never include news publications, media outlets, or trade publications (e.g. "The Real Deal", "Bloomberg", "Wall Street Journal") as companies_people entries — these are sources cited in the article, not deal participants

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
    t = title.lower()
    if any(excl in t for excl in _PROMOTION_EXCLUSIONS):
        return False
    return any(k in t for k in _PROMOTION_KEYWORDS)


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


def _normalize_sizes(summary: ArticleSummary) -> ArticleSummary:
    """When both size_sf and size_units are present, keep only the field that matches the transaction.
    Development/Construction and multi-dimension articles are left untouched."""
    if not summary.data_points:
        return summary
    dp = summary.data_points
    if not (dp.size_sf and dp.size_units):
        return summary
    if dp.size_beds or dp.size_keys:
        return summary
    tx = (summary.transaction_type or '').lower()
    # Development and construction legitimately show both SF (commercial component)
    # and units (residential component) — leave both in place
    if tx in ('development', 'construction'):
        return summary
    prop = (dp.property_type or '').lower()
    is_residential = any(t in prop for t in (
        'multifamily', 'condo', 'apartment', 'residential', 'senior', 'student', 'townhome'
    ))
    if tx == 'lease' or (tx in ('sale', 'acquisition') and not is_residential):
        dp.size_units = None
    else:
        dp.size_sf = None
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
  * IMPORTANT: only include the person(s) being newly hired, promoted, or appointed — do NOT include existing colleagues, supervisors, or team members mentioned only as context (e.g. "joining the team of X and Y" — X and Y should not be included)
  * IMPORTANT: only include people at firms that are direct CRE principals — developers, owners/investors, brokers/advisors, lenders, asset managers, REITs, or CRE-focused private equity. Do NOT include people at proptech, parking, mobility, data/analytics, or other technology or service companies that sell products or services to CRE clients but are not themselves real estate principals — if the firm is not a CRE principal, leave companies_people empty and set transaction_type to null
  * IMPORTANT: only include people in direct commercial real estate roles (broker, asset manager, investment manager, development, capital markets, leasing, property management, acquisitions, etc.). Do NOT include people in HR, IT, marketing, legal, architecture/design, or other support functions at a CRE firm — if the person's new role is not a CRE function, leave companies_people empty and set transaction_type to null
  * IMPORTANT: if the article is about a firm being appointed or selected to provide services (e.g. appointed as leasing agent, selected as property manager, awarded a management contract) rather than an individual being hired or promoted, this is not a Promotion — leave companies_people empty and set transaction_type to null
  * IMPORTANT: a "brokerage engagement" or "listing appointment" — where a property owner hires a broker to represent a sale or listing — is not a Promotion. If the article is about an individual being retained/engaged to broker a specific deal, leave companies_people empty and set transaction_type to null

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
                thinking_config=types.ThinkingConfig(thinking_budget=0),
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
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )
        )

    summary = ArticleSummary.model_validate_json(response.text)
    summary = _normalize_tx_type(summary)
    summary = _normalize_occupancy(summary)
    summary = _normalize_sizes(summary)
    return summary
