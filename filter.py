import re
from models import ArticleSummary

# Individual publication honors — always exempt from award/promotion filtering
_HONOR_PATTERNS = [
    'power 100', '30 under 30', '40 under 40', '50 under 40', '20 under 40',
    'broker of the year', 'executive of the year', 'hall of fame',
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
    r'\bboma\b.{0,30}\bannounce',
    r'\bnaiop\b.{0,30}\bannounce',
    r'\bnar\b.{0,30}\bannounce',
    r'\bcre[i]?\b.{0,30}\bannounce',
]

# Non-CRE content detectable from the title alone
_TITLE_NONCRE_PATTERNS = [
    r'\bnational \w[\w ]{0,35}week\b',        # "National Property Managers Week" etc.
    r'\binvesting.{0,25}\byouth\b',            # City youth investment ("Investing Big In Its Youth")
    r'\bschool district\b.{0,40}\bbond\b',     # School district bond articles
]

# Promotion seniority — senior signals (keep)
_SENIOR_KEYWORDS = [
    'managing director', 'partner', 'principal', 'president', 'chief ',
    'ceo', 'cfo', 'coo', 'cio', 'cto',
    'executive vice president', 'evp',
    'senior vice president', 'svp',
    'head of ', 'chairman', 'chairwoman',
    'founder', 'co-founder', 'managing partner',
    'market leader', 'office head', 'regional director',
    'power 100', '30 under 30', '40 under 40', '50 under 40', '20 under 40',
]

# Promotion seniority — junior signals (filter if no senior signal present)
_JUNIOR_KEYWORDS = [
    'associate ', 'associates', 'analyst ', 'coordinator', 'specialist',
    'assistant ', 'administrator', 'director of marketing',
    'director of operations', 'property manager',
]


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

    # Award articles the model caught
    if 'award' in article_type:
        return "Property/Deal Award"

    # Association or organizational news
    if any(kw in article_type for kw in ('association', 'membership', 'organization')):
        return "Association News"

    # Event/conference announcements
    if any(kw in article_type for kw in ('event', 'conference', 'expo', 'symposium', 'webinar')):
        return "Industry Event"

    # Single-family residential and ranch properties — not CRE
    if summary.data_points:
        prop_type = (summary.data_points.property_type or '').lower()
        if any(t in prop_type for t in ('single family', 'single-family')):
            return "Non-CRE Content"
        if prop_type == 'ranch':
            return "Non-CRE Content"

    # All promotions are kept — display is compact (name/title/company/link only)
    if tx_type == 'promotion':
        return None

    return None
