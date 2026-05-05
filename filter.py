import re
from models import ArticleSummary

# Individual publication honors — always exempt from award/promotion filtering
_HONOR_PATTERNS = [
    'power 100', '30 under 30', '40 under 40', '50 under 40', '20 under 40',
    'broker of the year', 'executive of the year',
    'most influential', 'top broker', 'top producer', 'rising star',
]

# Title-level pre-filters (checked before any API call)
_TITLE_AWARD_PATTERNS = [
    r'\btoby\b',
    r'\boutstanding building of the year\b',
    r'award winner',
    r'award recipients',
    r'award honoree',
    r'\bdeals? of the year\b',
    r'best transaction',
    r'regional winner',
    r'international winner',
    r'excellence award',         # "Chicagoland Apartment Marketing and Management Excellence Awards"
    r'\bcamme\b',                # Chicagoland Apartment Marketing & Management Excellence
    r'\bamma\b',                 # Apartment Association awards
    r'takes home.{0,30}honor',  # "takes home several honors"
    r'\bhonored.{0,20}award',
    r'\bhall of fame\b',         # Career induction awards (e.g. "CRE Hall of Fame: Sal Caldarone")
]

_TITLE_EVENT_PATTERNS = [
    r'\bannual conference\b',
    r'\bindustry conference\b',
    r'conference & expo',
    r'conference and expo',
    r'\bexpo\b.*\bregister\b',
    r'\bsymposium\b',
    r'\bwebinar\b',
    r'\bpanel discussion\b',
]

_TITLE_ASSOCIATION_PATTERNS = [
    r'\bboma\b.{0,40}\b(announce|elect|appoint|name)s?\b',
    r'\bnaiop\b.{0,40}\b(announce|elect|appoint|name)s?\b',
    r'\bnar\b.{0,40}\b(announce|elect|appoint|name)s?\b',
    r'\bcre[i]?\b.{0,40}\b(announce|elect|appoint|name)s?\b',
]

# Non-CRE content detectable from the title alone
_TITLE_NONCRE_PATTERNS = [
    r'\bnational \w[\w ]{0,35}week\b',        # "National Property Managers Week" etc.
    r'\binvesting.{0,25}\byouth\b',            # City youth investment ("Investing Big In Its Youth")
    r'\bschool district\b.{0,40}\bbond\b',     # School district bond articles
]

# Vendor/advisory list content — opinion pieces structured as numbered tips/issues lists
_TITLE_ADVISORY_PATTERNS = [
    r'^\d+\s+(issues?|tips?|ways?|steps?|reasons?|things?|mistakes?|strategies?|factors?)\b',
    r'^(how|why|what).{0,60}\?.*hint\b',       # clickbait editorial with "Hint:" subhead
]

# Contractor/vendor PR announcements — trade press completion notices of low editorial value
_TITLE_CONTRACTOR_PR_PATTERNS = [
    r'\bcompletes?\b.{0,60}\binterior\s+(construction|renovation|buildout|build-out)\b',
    r'\bcompletes?\b.{0,60}\boffice\s+interior\b',
]

# REIT/CRE corporate governance — shareholder votes, activist campaigns, board elections
_TITLE_CORPORATE_GOVERNANCE_PATTERNS = [
    r'\bboard\b.{0,40}\breelected\b',
    r'\bproxy\s+fight\b',
    r'\bactivist\b.{0,40}\b(campaign|investor)\b.{0,40}\b(reit|fund|trust|board)\b',
    r'\bshareholder\s+vote\b.{0,40}\b(reit|board|director)\b',
]

# Celebrity personal residential transactions — athlete/entertainer buying or listing their home
_TITLE_CELEBRITY_RESIDENTIAL_PATTERNS = [
    # Casual residential slang that only appears in celebrity home coverage
    r'\b(his|her|their)\b.{0,40}\b(pad|digs|crib)\b',
    # Sports league affiliation + residential listing/sale action
    r'\b(nba|nfl|nhl|mlb|mls|wnba)\b.{0,80}\b(relists?|lists?\s+\w{0,30}\s*(pad|condo|home|penthouse|apartment|house)|buys?\s+\w{0,30}\s*(pad|condo|home|penthouse|apartment))\b',
]

# Non-US/Canada location markers — single-country non-US/CA stories are filtered
_NON_US_CA_MARKERS = frozenset([
    'uk', 'u.k.', 'united kingdom', 'england', 'scotland', 'wales',
    'ireland', 'germany', 'france', 'spain', 'italy', 'portugal',
    'netherlands', 'belgium', 'switzerland', 'austria', 'poland',
    'sweden', 'norway', 'denmark', 'finland', 'czech',
    'australia', 'new zealand', 'china', 'japan', 'south korea',
    'singapore', 'hong kong', 'india', 'uae', 'dubai',
    'saudi arabia', 'saudi', 'mexico', 'brazil', 'argentina',
    'colombia', 'chile', 'peru', 'israel', 'turkey',
    'london', 'paris', 'berlin', 'amsterdam', 'madrid', 'rome',
    'barcelona', 'lisbon', 'dublin', 'tokyo', 'sydney', 'melbourne',
    'zurich', 'munich', 'frankfurt',
])

# Whole-word regex — prevents "india" matching "Indianapolis", "peru" matching "Perth Amboy", etc.
_NON_US_CA_RE = re.compile(
    r'\b(?:' + '|'.join(re.escape(m) for m in sorted(_NON_US_CA_MARKERS, key=len, reverse=True)) + r')\b'
)

# US cities that share names with non-US markers
_US_CITY_MARKET_EXCEPTIONS = frozenset([
    'rome, ga', 'rome, ny', 'berlin, nh', 'berlin, wi', 'berlin, md',
    'dublin, ca', 'dublin, oh', 'dublin, tx', 'dublin, pa',
    'peru, in', 'turkey, tx', 'china, tx', 'india, in',
])


def _is_non_us_canada_market(market: str | None) -> bool:
    if not market:
        return False
    m = market.lower()
    # Keep broad multi-market or international stories
    if any(x in m for x in ('international', 'global', 'north america', 'multi-market', 'national')):
        return False
    # London, Ontario is Canadian — keep
    if 'london' in m and ('ontario' in m or ', on' in m):
        return False
    # Amsterdam, New York is a US city — keep
    if 'amsterdam' in m and ('new york' in m or ', ny' in m):
        return False
    # US cities whose names overlap with non-US markers
    if any(exc in m for exc in _US_CITY_MARKET_EXCEPTIONS):
        return False
    return bool(_NON_US_CA_RE.search(m))


def _has_honor_exemption(title: str) -> bool:
    t = title.lower()
    return any(h in t for h in _HONOR_PATTERNS)


def get_title_filter_reason(title: str) -> str | None:
    """
    Quick title-level check before any API call.
    Returns a filter reason string, or None if the article should proceed.
    """
    if _has_honor_exemption(title):
        return None

    t = title.lower()

    for pattern in _TITLE_AWARD_PATTERNS:
        if re.search(pattern, t):
            return "Property/Deal Award"

    for pattern in _TITLE_EVENT_PATTERNS:
        if re.search(pattern, t):
            return "Industry Event"

    for pattern in _TITLE_ASSOCIATION_PATTERNS:
        if re.search(pattern, t):
            return "Association News"

    for pattern in _TITLE_NONCRE_PATTERNS:
        if re.search(pattern, t):
            return "Non-CRE Content"

    for pattern in _TITLE_ADVISORY_PATTERNS:
        if re.search(pattern, t):
            return "Vendor/Advisory Content"

    for pattern in _TITLE_CONTRACTOR_PR_PATTERNS:
        if re.search(pattern, t):
            return "Vendor/Advisory Content"

    for pattern in _TITLE_CORPORATE_GOVERNANCE_PATTERNS:
        if re.search(pattern, t):
            return "Non-CRE Content"

    for pattern in _TITLE_CELEBRITY_RESIDENTIAL_PATTERNS:
        if re.search(pattern, t):
            return "Non-CRE Content"

    return None


def get_summary_filter_reason(article: dict, summary: ArticleSummary) -> str | None:
    """
    Post-summary check using the model's article_type and transaction_type.
    Returns a filter reason string, or None if the article should display normally.
    """
    title = article.get('title', '')
    if _has_honor_exemption(title):
        return None

    article_type = (summary.article_type or '').lower()
    tx_type = (summary.transaction_type or '').lower()

    # Non-CRE content
    if 'non-cre' in article_type:
        return "Non-CRE Content"

    # Celebrity individual residential transactions (athlete/entertainer buying or selling personal home)
    if 'celebrity residential' in article_type:
        return "Non-CRE Content"

    # Pure opinion/editorial columns with no market data or reporting
    if 'opinion / editorial' in article_type:
        return "Opinion/Editorial Content"

    # Government/civic property use (city halls, courthouses, etc.)
    if any(kw in article_type for kw in ('government use', 'civic', 'government / civic')):
        return "Non-CRE Content"

    # Crime, arrest, or political protest articles
    if any(kw in article_type for kw in ('crime', 'arrest', 'political protest', 'political / crime')):
        return "Non-CRE Content"

    # Obituaries
    if 'obituary' in article_type:
        return "Non-CRE Content"

    # Award articles the model caught
    if 'award' in article_type:
        return "Property/Deal Award"

    # Association or organizational news
    if any(kw in article_type for kw in ('association', 'membership', 'organization')):
        return "Association News"

    # Event/conference announcements
    if any(kw in article_type for kw in ('event', 'conference', 'expo', 'symposium', 'webinar')):
        return "Industry Event"

    # Political, electoral, or campaign finance articles
    if any(kw in article_type for kw in ('political', 'campaign finance', 'electoral')):
        return "Non-CRE Content"

    # Single-family residential, estates, ranches — individual home transactions, not CRE asset class
    if summary.data_points:
        prop_type = (summary.data_points.property_type or '').lower()
        if any(t in prop_type for t in ('single family', 'single-family', 'estate', 'mansion')):
            return "Non-CRE Content"
        if prop_type == 'ranch':
            return "Non-CRE Content"

    # Non-US/Canada single-country stories
    if _is_non_us_canada_market(summary.market):
        return "Non-US Market"

    # Soft feature / profile / Q&A content
    if any(kw in article_type for kw in ('feature / profile', 'q&a', 'interview', 'profile / q&a')):
        return "Feature/Profile Content"

    # Minimum deal size — only applied when a price is explicitly stated
    _MIN_DEAL_DOLLARS = 1_000_000
    if summary.data_points:
        dp = summary.data_points
        if tx_type in ('sale', 'acquisition') and dp.sale_price and dp.sale_price < _MIN_DEAL_DOLLARS:
            return "Below Minimum Deal Size"
        if tx_type in ('loan', 'refinance') and dp.loan_amount and dp.loan_amount < _MIN_DEAL_DOLLARS:
            return "Below Minimum Deal Size"

    # Low-value lease — two independent rules:
    # 1. Too small to matter regardless of other data
    # 2. No rate and no named tenant — no comp value at any size
    if tx_type == 'lease':
        dp = summary.data_points
        sf = dp.size_sf if dp else None
        has_rate = bool(dp and dp.rental_rate)
        has_tenant = bool(summary.tenants)
        if sf is not None and sf < 1000:
            return "Low-Value Lease"
        if not has_rate and not has_tenant:
            return "Low-Value Lease"

    return None
