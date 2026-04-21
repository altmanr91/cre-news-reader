import os
import re
import smtplib
import urllib.parse
import webbrowser
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

from rss_fetcher import fetch_articles
from article_scraper import get_full_article_text
from summarizer import get_summary
from geocoder import inject_geocoded_address
from calculator import inject_calculated_metrics
from filter import get_title_filter_reason, get_summary_filter_reason
from models import ArticleSummary

load_dotenv()

ARTICLES_PER_FEED = 5
RECIPIENT = os.getenv('DIGEST_RECIPIENT', 'altmanr91@gmail.com')
SENDER    = os.getenv('DIGEST_SENDER',    'altmanr91@gmail.com')


def _fmt_dollars(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.2f}B".rstrip('0').rstrip('.')
    if value >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:,.0f}K"
    return f"${value:,.0f}"


def _line(text: str) -> str:
    return f'<p style="margin:2px 0 2px 14px;font-size:0.88em;">{text}</p>'


def _collapsible(label: str, content: str, expanded: bool = False) -> str:
    if not content.strip():
        return ''
    open_attr = ' open' if expanded else ''
    return (
        f'<details class="section-detail"{open_attr}>'
        f'<summary>{label}</summary>'
        f'<div>{content}</div>'
        f'</details>'
    )


def _render_article_html(article: dict, summary: ArticleSummary, expanded: bool = False) -> str:
    is_promotion = (summary.transaction_type or '').lower() == 'promotion'
    is_market    = bool(summary.article_type) and not summary.transaction_type

    title     = article.get('title', '')
    link      = article.get('link', '#')
    source    = article.get('source', '')
    published = article.get('published', '')

    header = (
        f'<h3 style="margin:0 0 2px;font-size:1em;">'
        f'<a href="{link}" style="color:#1a1a1a;text-decoration:none;">{title}</a></h3>'
        f'<p style="color:#777;font-size:0.8em;margin:0 0 6px;">{source} &mdash; {published}</p>'
    )

    if is_promotion:
        return header

    sections = []

    # SUMMARY
    if summary.narrative:
        narrative_html = f'<p style="margin:0;line-height:1.55;font-size:0.9em;">{summary.narrative}</p>'
        # Article type label for non-transaction articles
        if summary.article_type:
            narrative_html = (
                f'<p style="margin:0 0 6px;font-size:0.82em;color:#555;font-style:italic;">'
                f'{summary.article_type}</p>'
            ) + narrative_html
        sections.append(_collapsible('SUMMARY', narrative_html, expanded))

    # DATA POINTS
    dp = summary.data_points
    dp_lines = []
    if dp and not is_market:
        if dp.property_type:
            dp_lines.append(_line(f'Property Type: {dp.property_type}'))
        if dp.property_name:
            dp_lines.append(_line(f'Property Name: {dp.property_name}'))
        if dp.address:
            maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(dp.address)}"
            addr_text = f'Address: <a href="{maps_url}" style="color:#1a1a1a;">{dp.address}</a>'
            if dp.address_sourced_separately:
                addr_text += '*'
            dp_lines.append(_line(addr_text))
        if dp.size_sf:
            dp_lines.append(_line(f'Size: {dp.size_sf:,.0f} SF'))
        if dp.size_units:
            dp_lines.append(_line(f'Size: {dp.size_units:,} units'))
        if dp.size_beds:
            dp_lines.append(_line(f'Beds: {dp.size_beds:,}'))
        if dp.size_keys:
            dp_lines.append(_line(f'Keys: {dp.size_keys:,}'))
        if dp.sale_price:
            dp_lines.append(_line(f'Sale Price: {_fmt_dollars(dp.sale_price)}'))
        if dp.loan_amount:
            dp_lines.append(_line(f'Loan Amount: {_fmt_dollars(dp.loan_amount)}'))
        if dp.total_project_cost:
            dp_lines.append(_line(f'Total Project Cost: {_fmt_dollars(dp.total_project_cost)}'))
        for lbl, val in inject_calculated_metrics(summary).items():
            dp_lines.append(_line(f'{lbl}: {val}'))
        if dp.occupancy is not None:
            tt = (summary.transaction_type or '').lower()
            if 'sale' in tt or 'acquisition' in tt:
                occ_label = 'Occupancy at Sale'
            elif 'loan' in tt or 'refinance' in tt:
                occ_label = 'Occupancy at Close'
            else:
                occ_label = 'Current Occupancy'
            dp_lines.append(_line(f'{occ_label}: {dp.occupancy}%'))
        if dp.year_built:
            dp_lines.append(_line(f'Year Built: {dp.year_built}'))
        if dp.completion:
            dp_lines.append(_line(f'Completion: {dp.completion}'))
        if dp.phase_1:
            dp_lines.append(_line(f'Phase I: {dp.phase_1}'))
        if dp.total_project_all_phases:
            dp_lines.append(_line(f'Total Project (All Phases): {dp.total_project_all_phases}'))
        if dp.original_plan:
            dp_lines.append(_line(f'Original Plan: {dp.original_plan}'))
        if dp.notable_features:
            dp_lines.append(_line(f'Notable Features: {dp.notable_features}'))
        if dp.project_notes:
            dp_lines.append(_line(f'Project Notes: {dp.project_notes}'))
        if dp.address_sourced_separately:
            dp_lines.append(
                '<p style="font-size:0.78em;font-style:italic;margin:3px 0 0 14px;">'
                '* Address sourced separately, not in original article.</p>'
            )

    # KEY DATA POINTS (market/research articles)
    if summary.key_data_points and is_market:
        for kdp in summary.key_data_points:
            dp_lines.append(_line(f'{kdp.label}: {kdp.value}'))

    if dp_lines:
        sections.append(_collapsible('DATA POINTS', ''.join(dp_lines), expanded))

    # COMPANIES/PEOPLE
    cp_lines = []
    if summary.companies_people and not is_market:
        seen_firms = set()
        for entry in summary.companies_people:
            if 'undisclosed' in entry.firm_name.lower():
                continue
            firm_key = entry.firm_name.lower().split()[0]
            if firm_key in seen_firms:
                continue
            seen_firms.add(firm_key)
            if entry.people:
                people_str = '; '.join(
                    f'{p.name}, {p.title}' if p.title else p.name
                    for p in entry.people
                )
                cp_lines.append(_line(f'{entry.label}: {entry.firm_name} \u2014 {people_str}'))
            else:
                cp_lines.append(_line(f'{entry.label}: {entry.firm_name}'))
    if cp_lines:
        sections.append(_collapsible('COMPANIES/PEOPLE', ''.join(cp_lines), expanded))

    # TENANTS
    if summary.tenants:
        tenant_lines = ''.join(_line(t) for t in summary.tenants)
        sections.append(_collapsible('TENANTS AT PROPERTY', tenant_lines, expanded))

    # FINANCING
    if summary.financing:
        sections.append(_collapsible('FINANCING',
            f'<p style="margin:0 0 4px 14px;font-size:0.88em;">{summary.financing}</p>', expanded))

    # SPONSOR PIPELINE
    _pipeline_skip = ['vanderbilt', 'university', 'satellite campus', 'lobbied', 'convinced']
    filtered_pipeline = [
        p for p in summary.sponsor_pipeline
        if not any(kw in (p.name_or_address + ' ' + p.description).lower() for kw in _pipeline_skip)
    ]
    if filtered_pipeline:
        pipeline_lines = ''.join(_line(f'{p.name_or_address}: {p.description}') for p in filtered_pipeline)
        sections.append(_collapsible('SPONSOR PIPELINE', pipeline_lines, expanded))

    # MARKET INTELLIGENCE
    if summary.market_intelligence:
        sections.append(_collapsible('MARKET INTELLIGENCE',
            f'<p style="margin:0 0 4px 14px;font-size:0.88em;">{summary.market_intelligence}</p>', expanded))

    return header + ''.join(sections)


_MARKET_PRIORITY = {
    # Northeast
    'manhattan': 1, 'new york': 1, 'brooklyn': 2, 'queens': 3, 'bronx': 3,
    'boston': 4, 'philadelphia': 5, 'pittsburgh': 6, 'newark': 7,
    # Mid-Atlantic
    'washington': 1, 'd.c.': 1, 'northern virginia': 2, 'baltimore': 3,
    # Southeast
    'miami': 1, 'atlanta': 2, 'charlotte': 3, 'nashville': 4, 'raleigh': 5,
    'orlando': 6, 'tampa': 7, 'jacksonville': 8, 'charleston': 9, 'memphis': 10,
    # Midwest
    'chicago': 1, 'minneapolis': 2, 'detroit': 3, 'indianapolis': 4,
    'columbus': 5, 'kansas city': 6, 'st. louis': 7, 'cleveland': 8,
    'milwaukee': 9, 'cincinnati': 10, 'omaha': 11,
    # Texas
    'dallas': 1, 'houston': 2, 'austin': 3, 'san antonio': 4, 'fort worth': 5,
    # Mountain West
    'phoenix': 1, 'denver': 2, 'las vegas': 3, 'salt lake': 4,
    'scottsdale': 5, 'tucson': 6, 'albuquerque': 7, 'oklahoma city': 8,
    # West Coast
    'los angeles': 1, 'san francisco': 2, 'seattle': 3, 'san diego': 4,
    'portland': 5, 'sacramento': 6, 'san jose': 7, 'oakland': 8,
}


def _market_sort_key(market: str) -> int:
    m = market.lower()
    for city, priority in _MARKET_PRIORITY.items():
        if city in m:
            return priority
    return 999


_TYPE_ORDER = [
    'Market Intelligence',
    'Sales & Acquisitions',
    'Financing',
    'Development & Construction',
    'Leases',
    'People',
]

_REGION_ORDER = [
    'National / Multi-Market',
    'Northeast',
    'Mid-Atlantic',
    'Southeast',
    'Midwest',
    'Texas',
    'Mountain West',
    'West Coast',
    'Other',
]

_STATE_TO_REGION = {
    'ny': 'Northeast',   'nj': 'Northeast',  'ct': 'Northeast',
    'ma': 'Northeast',   'ri': 'Northeast',  'vt': 'Northeast',
    'nh': 'Northeast',   'me': 'Northeast',  'pa': 'Northeast',
    'md': 'Mid-Atlantic','va': 'Mid-Atlantic','de': 'Mid-Atlantic',
    'wv': 'Mid-Atlantic','dc': 'Mid-Atlantic',
    'fl': 'Southeast',   'ga': 'Southeast',  'nc': 'Southeast',
    'sc': 'Southeast',   'tn': 'Southeast',  'ky': 'Southeast',
    'al': 'Southeast',   'ms': 'Southeast',  'ar': 'Southeast',
    'la': 'Southeast',
    'il': 'Midwest',     'oh': 'Midwest',    'mi': 'Midwest',
    'mn': 'Midwest',     'wi': 'Midwest',    'in': 'Midwest',
    'mo': 'Midwest',     'ia': 'Midwest',    'ks': 'Midwest',
    'ne': 'Midwest',     'nd': 'Midwest',    'sd': 'Midwest',
    'tx': 'Texas',
    'co': 'Mountain West','az': 'Mountain West','nv': 'Mountain West',
    'nm': 'Mountain West','ut': 'Mountain West','wy': 'Mountain West',
    'mt': 'Mountain West','id': 'Mountain West','ok': 'Mountain West',
    'ca': 'West Coast',  'wa': 'West Coast', 'or': 'West Coast',
    'hi': 'West Coast',  'ak': 'West Coast',
}

_STATE_NAMES_TO_REGION = {
    'new york': 'Northeast',      'new jersey': 'Northeast',
    'connecticut': 'Northeast',   'massachusetts': 'Northeast',
    'rhode island': 'Northeast',  'vermont': 'Northeast',
    'new hampshire': 'Northeast', 'maine': 'Northeast',
    'pennsylvania': 'Northeast',
    'maryland': 'Mid-Atlantic',   'virginia': 'Mid-Atlantic',
    'delaware': 'Mid-Atlantic',   'west virginia': 'Mid-Atlantic',
    'florida': 'Southeast',       'georgia': 'Southeast',
    'north carolina': 'Southeast','south carolina': 'Southeast',
    'tennessee': 'Southeast',     'kentucky': 'Southeast',
    'alabama': 'Southeast',       'mississippi': 'Southeast',
    'arkansas': 'Southeast',      'louisiana': 'Southeast',
    'illinois': 'Midwest',        'ohio': 'Midwest',
    'michigan': 'Midwest',        'minnesota': 'Midwest',
    'wisconsin': 'Midwest',       'indiana': 'Midwest',
    'missouri': 'Midwest',        'iowa': 'Midwest',
    'kansas': 'Midwest',          'nebraska': 'Midwest',
    'north dakota': 'Midwest',    'south dakota': 'Midwest',
    'texas': 'Texas',
    'colorado': 'Mountain West',  'arizona': 'Mountain West',
    'nevada': 'Mountain West',    'new mexico': 'Mountain West',
    'utah': 'Mountain West',      'wyoming': 'Mountain West',
    'montana': 'Mountain West',   'idaho': 'Mountain West',
    'oklahoma': 'Mountain West',
    'california': 'West Coast',   'oregon': 'West Coast',
    'hawaii': 'West Coast',       'alaska': 'West Coast',
    'washington': 'West Coast',
}

_CITY_TO_REGION = {
    'manhattan': 'Northeast',    'brooklyn': 'Northeast',
    'bronx': 'Northeast',        'queens': 'Northeast',
    'boston': 'Northeast',       'philadelphia': 'Northeast',
    'pittsburgh': 'Northeast',   'newark': 'Northeast',
    'baltimore': 'Mid-Atlantic', 'washington d.c': 'Mid-Atlantic',
    'northern virginia': 'Mid-Atlantic',
    'miami': 'Southeast',        'orlando': 'Southeast',
    'tampa': 'Southeast',        'jacksonville': 'Southeast',
    'atlanta': 'Southeast',      'charlotte': 'Southeast',
    'raleigh': 'Southeast',      'nashville': 'Southeast',
    'charleston': 'Southeast',   'memphis': 'Southeast',
    'chicago': 'Midwest',        'cleveland': 'Midwest',
    'columbus': 'Midwest',       'detroit': 'Midwest',
    'minneapolis': 'Midwest',    'milwaukee': 'Midwest',
    'indianapolis': 'Midwest',   'st. louis': 'Midwest',
    'kansas city': 'Midwest',    'cincinnati': 'Midwest',
    'omaha': 'Midwest',
    'dallas': 'Texas',           'houston': 'Texas',
    'austin': 'Texas',           'san antonio': 'Texas',
    'fort worth': 'Texas',       'el paso': 'Texas',
    'denver': 'Mountain West',   'phoenix': 'Mountain West',
    'las vegas': 'Mountain West','salt lake': 'Mountain West',
    'tucson': 'Mountain West',   'albuquerque': 'Mountain West',
    'scottsdale': 'Mountain West','tempe': 'Mountain West',
    'los angeles': 'West Coast', 'san francisco': 'West Coast',
    'san diego': 'West Coast',   'seattle': 'West Coast',
    'portland': 'West Coast',    'sacramento': 'West Coast',
    'san jose': 'West Coast',    'oakland': 'West Coast',
}


def _market_to_region(market: str | None) -> str:
    if not market:
        return 'National / Multi-Market'
    m = market.lower()

    # DC check before generic "washington" (which maps to WA state)
    if any(x in m for x in ['d.c.', 'district of columbia', 'washington, d']):
        return 'Mid-Atlantic'

    # State abbreviation at end of string — handles ", NY" ", N.J." ", N.C." etc.
    abbr_match = re.search(r',\s*([a-z]\.?[a-z]\.?)\.?\s*$', m)
    if abbr_match:
        abbr = abbr_match.group(1).replace('.', '')
        region = _STATE_TO_REGION.get(abbr)
        if region:
            return region

    # Full state names
    for state_name, region in _STATE_NAMES_TO_REGION.items():
        if state_name in m:
            return region

    # City name fallback
    for city, region in _CITY_TO_REGION.items():
        if city in m:
            return region

    return 'National / Multi-Market'


def _type_category(summary: ArticleSummary) -> str:
    tx = (summary.transaction_type or '').lower()
    if tx in ('sale', 'acquisition'):
        return 'Sales & Acquisitions'
    if tx in ('loan', 'refinance'):
        return 'Financing'
    if tx in ('development', 'construction'):
        return 'Development & Construction'
    if tx == 'lease':
        return 'Leases'
    if tx == 'promotion':
        return 'People'
    return 'Market Intelligence'


def _render_people_html(entries: list) -> str:
    lines = []
    for article, summary in entries:
        link = article.get('link', '#')
        for entry in summary.companies_people:
            firm = entry.firm_name
            for person in entry.people:
                name  = person.name
                title = person.title
                text  = f'<strong>{name}</strong>'
                if title:
                    text += f', {title}'
                text += f' &mdash; {firm}'
                text += f' <a href="{link}" style="color:#aaa;font-size:0.82em;">[article]</a>'
                lines.append(f'<p style="margin:4px 0;">{text}</p>')
    return ''.join(lines) if lines else ''


def build_article_page(article: dict, summary: ArticleSummary, global_url: str) -> str:
    today  = datetime.now().strftime('%B %d, %Y')
    title  = article.get('title', '')
    source = article.get('source', '')
    published = article.get('published', '')

    back_link = (
        f'<p style="font-size:0.82em;margin:0 0 20px;">'
        f'<a href="{global_url}" style="color:#555;">&larr; Full Digest</a></p>'
    )
    article_html = _render_article_html(article, summary, expanded=True)

    css = """
    <style>
      body { font-family: Georgia, serif; max-width: 740px; margin: 0 auto; padding: 28px 20px; color: #1a1a1a; background: #fff; }
      a { color: #1a1a1a; }
      details { margin: 3px 0; }
      details > summary { list-style: none; cursor: pointer; }
      details > summary::-webkit-details-marker { display: none; }
      details.section-detail > summary { font-size: 0.8em; font-weight: bold; letter-spacing: 0.03em; color: #333; padding: 2px 0; font-family: Arial, sans-serif; }
      details.section-detail > div { padding: 4px 0 4px 8px; }
    </style>
    """

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  {css}
</head>
<body>
  {back_link}
  {article_html}
  <p style="font-size:0.72em;color:#ccc;margin-top:40px;">CRE News Reader &mdash; {today}</p>
</body>
</html>"""


def _render_article_email(article: dict, summary: ArticleSummary) -> str:
    """Narrative-only article block for the email digest."""
    is_promotion = (summary.transaction_type or '').lower() == 'promotion'
    title     = article.get('title', '')
    link      = article.get('link', '#')
    source    = article.get('source', '')
    published = article.get('published', '')

    header = (
        f'<h3 style="margin:0 0 2px;font-size:1em;">'
        f'<a href="{link}" style="color:#1a1a1a;text-decoration:none;">{title}</a></h3>'
        f'<p style="color:#777;font-size:0.8em;margin:0 0 5px;">{source} &mdash; {published}</p>'
    )

    if is_promotion:
        return header

    if summary.narrative:
        return header + (
            f'<p style="margin:0;line-height:1.55;font-size:0.9em;">{summary.narrative}</p>'
        )
    return header


def build_email_html(articles: list, results: list, global_url: str) -> str:
    today        = datetime.now().strftime('%B %d, %Y')
    source_count = len(set(a['source'] for a in articles))

    grouped: dict[str, dict[str, dict[str, list]]] = {t: {} for t in _TYPE_ORDER}

    for article, result in zip(articles, results):
        if result.get('filtered') or not result.get('summary'):
            continue
        summary  = result['summary']
        type_cat = _type_category(summary)
        if type_cat == 'People':
            grouped[type_cat].setdefault('_people', {}).setdefault('_all', []).append((article, summary))
        else:
            region = _market_to_region(summary.market)
            market = summary.market or 'National / Multi-Market'
            grouped[type_cat].setdefault(region, {}).setdefault(market, []).append((article, summary))

    shown_count = sum(
        len(items)
        for type_data in grouped.values()
        for markets in type_data.values()
        for items in markets.values()
    )

    body_parts = [
        f'<p style="font-size:0.85em;color:#555;margin:0 0 20px;padding:10px 14px;'
        f'background:#f5f5f5;border-left:3px solid #ccc;">'
        f'<a href="{global_url}" style="color:#1a1a1a;font-weight:bold;">View Full Digest</a> '
        f'&mdash; data points, companies &amp; market intelligence for all articles.</p>'
    ]

    for type_cat in _TYPE_ORDER:
        type_data = grouped[type_cat]
        if not type_data:
            continue

        body_parts.append(
            f'<h2 style="font-size:1em;letter-spacing:0.06em;margin:32px 0 12px;'
            f'padding-bottom:6px;border-bottom:2px solid #1a1a1a;">'
            f'{type_cat.upper()}</h2>'
        )

        if type_cat == 'People':
            all_entries = [item for items in type_data.get('_people', {}).values() for item in items]
            people_html = _render_people_html(all_entries)
            if people_html:
                body_parts.append(f'<div style="margin-bottom:20px;">{people_html}</div>')
        else:
            for region in _REGION_ORDER:
                markets = type_data.get(region, {})
                if not markets:
                    continue
                body_parts.append(
                    f'<h3 style="font-size:0.82em;letter-spacing:0.05em;color:#555;'
                    f'margin:20px 0 6px;font-family:Arial,sans-serif;">'
                    f'{region.upper()}</h3>'
                )
                for market in sorted(markets.keys(), key=_market_sort_key):
                    items = markets[market]
                    body_parts.append(
                        f'<p style="font-size:0.78em;font-weight:bold;letter-spacing:0.04em;'
                        f'color:#888;margin:10px 0 8px;font-family:Arial,sans-serif;">'
                        f'MARKET: {market.upper()}</p>'
                    )
                    for article, summary in items:
                        page_url = article.get('page_url', '')
                        detail_link = (
                            f' <a href="{page_url}" style="font-size:0.8em;color:#888;'
                            f'text-decoration:none;font-family:Arial,sans-serif;">Details &rarr;</a>'
                            if page_url else ''
                        )
                        body_parts.append(
                            f'<div style="margin-bottom:16px;">'
                            f'{_render_article_email(article, summary)}'
                            f'{detail_link}</div>'
                            f'<hr style="border:none;border-top:1px solid #e8e8e8;margin:4px 0 16px;">'
                        )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:Georgia,serif;max-width:680px;margin:0 auto;padding:24px 16px;color:#1a1a1a;background:#ffffff;-webkit-text-size-adjust:100%;">
  <h1 style="font-size:1.35em;margin:0 0 2px;padding-bottom:8px;border-bottom:2px solid #1a1a1a;">CRE News Digest</h1>
  <p style="color:#777;font-size:0.85em;margin:6px 0 16px;">{today} &mdash; {shown_count} articles from {source_count} sources</p>
  {"".join(body_parts)}
  <p style="font-size:0.72em;color:#bbb;margin-top:36px;text-align:center;">CRE News Reader &mdash; {today}</p>
</body>
</html>"""


def build_browser_html(articles: list, results: list) -> str:
    today        = datetime.now().strftime('%B %d, %Y')
    source_count = len(set(a['source'] for a in articles))

    # Same grouping logic as build_digest_html
    grouped: dict[str, dict[str, dict[str, list]]] = {t: {} for t in _TYPE_ORDER}
    filtered_items = []

    for article, result in zip(articles, results):
        if result.get('filtered'):
            filtered_items.append((result['filter_reason'], article.get('title', ''), article.get('link', '#')))
            continue
        if not result.get('summary'):
            continue
        summary  = result['summary']
        type_cat = _type_category(summary)
        if type_cat == 'People':
            grouped[type_cat].setdefault('_people', {}).setdefault('_all', []).append((article, summary))
        else:
            region = _market_to_region(summary.market)
            market = summary.market or 'National / Multi-Market'
            grouped[type_cat].setdefault(region, {}).setdefault(market, []).append((article, summary))

    shown_count = sum(
        len(items)
        for type_data in grouped.values()
        for markets in type_data.values()
        for items in markets.values()
    )

    body_parts = []
    for type_cat in _TYPE_ORDER:
        type_data = grouped[type_cat]
        if not type_data:
            continue

        if type_cat == 'People':
            all_entries = [item for items in type_data.get('_people', {}).values() for item in items]
            people_html = _render_people_html(all_entries)
            if not people_html:
                continue
            body_parts.append(
                f'<h2 class="type-header">{type_cat.upper()}</h2>'
                f'<div class="type-body">{people_html}</div>'
            )
        else:
            region_parts = []
            for region in _REGION_ORDER:
                markets = type_data.get(region, {})
                if not markets:
                    continue
                market_parts = []
                for market in sorted(markets.keys(), key=_market_sort_key):
                    items = markets[market]
                    article_parts = []
                    for article, summary in items:
                        article_parts.append(
                            f'<div class="article">{_render_article_html(article, summary)}</div>'
                        )
                    market_parts.append(
                        f'<p class="market-header">MARKET: {market.upper()}</p>'
                        f'<div class="market-body">{"".join(article_parts)}</div>'
                    )
                region_parts.append(
                    f'<h3 class="region-header">{region.upper()}</h3>'
                    f'<div class="region-body">{"".join(market_parts)}</div>'
                )
            if region_parts:
                body_parts.append(
                    f'<h2 class="type-header">{type_cat.upper()}</h2>'
                    f'<div class="type-body">{"".join(region_parts)}</div>'
                )

    filtered_section = ''
    if filtered_items:
        li_items = ''.join(
            f'<li><a href="{link}" target="_blank">{title}</a> <span class="filter-reason">({reason})</span></li>'
            for reason, title, link in filtered_items
        )
        filtered_section = (
            f'<details><summary class="filter-header">FILTERED ({len(filtered_items)})</summary>'
            f'<ul class="filter-list">{li_items}</ul></details>'
        )

    css = """
    <style>
      body { font-family: Georgia, serif; max-width: 780px; margin: 0 auto; padding: 24px 20px; color: #1a1a1a; background: #fff; }
      h1 { font-size: 1.4em; margin: 0 0 4px; padding-bottom: 10px; border-bottom: 2px solid #1a1a1a; }
      .meta { color: #777; font-size: 0.85em; margin: 6px 0 20px; }

      details { margin: 0; }
      details > summary { list-style: none; cursor: pointer; user-select: none; }
      details > summary::-webkit-details-marker { display: none; }
      details > summary::before { content: '▶ '; font-size: 0.7em; color: #888; transition: transform 0.15s; display: inline-block; }
      details[open] > summary::before { content: '▼ '; }

      .type-header { font-size: 0.95em; font-weight: bold; letter-spacing: 0.07em; padding: 10px 0 8px; border-bottom: 2px solid #1a1a1a; margin: 28px 0 0; display: block; }
      .type-body { padding: 4px 0 0 0; }

      .region-header { font-size: 0.78em; font-weight: bold; letter-spacing: 0.06em; color: #444; padding: 12px 0 6px; border-bottom: 1px solid #ccc; margin: 0; display: block; font-family: Arial, sans-serif; }
      .region-body { padding: 4px 0 0 12px; }

      .market-header { font-size: 0.72em; font-weight: bold; letter-spacing: 0.05em; color: #888; padding: 8px 0 4px; display: block; font-family: Arial, sans-serif; }
      .market-body { padding: 0 0 0 12px; }

      .article { border-bottom: 1px solid #eee; padding: 10px 0 10px; margin-bottom: 0; }
      .article:last-child { border-bottom: none; }
      .article h3 { font-size: 0.98em; margin: 0 0 2px; }
      .article h3 a { color: #1a1a1a; text-decoration: none; }
      .article h3 a:hover { text-decoration: underline; }
      .article .pub { color: #888; font-size: 0.78em; margin: 0 0 5px; }

      details.section-detail { margin: 3px 0; }
      details.section-detail > summary { font-size: 0.8em; font-weight: bold; letter-spacing: 0.03em; color: #333; padding: 2px 0; font-family: Arial, sans-serif; }
      details.section-detail > div { padding: 4px 0 4px 8px; font-size: 0.88em; }
      .dp-line { margin: 2px 0 2px 10px; font-size: 0.88em; }
      .dp-line a { color: #1a1a1a; }
      .footnote { font-size: 0.78em; font-style: italic; margin: 3px 0 0 10px; color: #666; }
      .article-type-label { font-size: 0.8em; color: #555; font-style: italic; margin: 0 0 5px; }

      .filter-header { font-size: 0.75em; font-weight: bold; letter-spacing: 0.05em; color: #bbb; padding: 6px 0; font-family: Arial, sans-serif; margin-top: 32px; display: block; }
      .filter-list { font-size: 0.82em; color: #aaa; padding-left: 18px; margin: 4px 0; }
      .filter-list a { color: #aaa; }
      .filter-reason { font-size: 0.88em; }

      .people-line { margin: 4px 0; font-size: 0.9em; }
      .people-line a { color: #aaa; font-size: 0.82em; }
    </style>
    """

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>CRE News Digest — {today}</title>
  {css}
</head>
<body>
  <h1>CRE News Digest</h1>
  <p class="meta">{today} &mdash; {shown_count} articles from {source_count} sources</p>
  {"".join(body_parts)}
  {filtered_section}
  <p style="font-size:0.72em;color:#ccc;margin-top:40px;text-align:center;">CRE News Reader &mdash; {today}</p>
</body>
</html>"""


def run_pipeline(articles_per_feed: int = ARTICLES_PER_FEED) -> tuple[list, list]:
    print(f"Fetching articles ({articles_per_feed} per feed)...")
    articles = fetch_articles(max_articles_per_feed=articles_per_feed)
    print(f"  {len(articles)} articles fetched from {len(set(a['source'] for a in articles))} sources")

    results = []
    for i, article in enumerate(articles):
        print(f"  [{i+1}/{len(articles)}] {article['title'][:70]}...")

        pre_filter = get_title_filter_reason(article['title'])
        if pre_filter:
            print(f"    -> Filtered (title): {pre_filter}")
            results.append({'filtered': True, 'filter_reason': pre_filter})
            continue

        full_text = get_full_article_text(article['link'])
        article['full_text']     = full_text
        article['has_full_text'] = full_text is not None

        content = article['full_text'] if article['has_full_text'] else article['summary']

        try:
            summary = get_summary(article['title'], content, article.get('published'))
            summary = inject_geocoded_address(summary)

            post_filter = get_summary_filter_reason(article, summary)
            if post_filter:
                print(f"    -> Filtered (summary): {post_filter}")
                results.append({'filtered': True, 'filter_reason': post_filter})
            else:
                results.append({'summary': summary})
        except Exception as e:
            print(f"    -> Error: {e}")
            results.append({'error': str(e)})

    shown = sum(1 for r in results if r.get('summary'))
    filtered = sum(1 for r in results if r.get('filtered'))
    print(f"\nPipeline complete: {shown} articles to send, {filtered} filtered")
    return articles, results


def send_digest(html_body: str, subject: str) -> int:
    app_password = os.getenv('GMAIL_APP_PASSWORD')
    if not app_password:
        raise RuntimeError("GMAIL_APP_PASSWORD not set in .env")

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = SENDER
    msg['To']      = RECIPIENT
    msg.attach(MIMEText(html_body, 'html'))

    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login(SENDER, app_password)
        server.sendmail(SENDER, RECIPIENT, msg.as_string())

    return 250


def _restart_server(directory: str, port: int) -> None:
    import subprocess
    import signal

    pid_file = os.path.join(directory, 'digest_server.pid')
    python   = os.path.join(directory, 'venv', 'Scripts', 'pythonw.exe')
    server   = os.path.join(directory, 'server.py')

    # Kill existing server if running
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, signal.SIGTERM)
        except (ProcessLookupError, ValueError, OSError):
            pass
        os.remove(pid_file)

    # Start new server detached (no console window on Windows)
    proc = subprocess.Popen(
        [python, server],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )
    with open(pid_file, 'w') as f:
        f.write(str(proc.pid))
    print(f"HTTP server started (pid {proc.pid}) at http://localhost:{port}")


def main():
    articles, results = run_pipeline()

    today     = datetime.now().strftime('%B %d, %Y')
    date_slug = datetime.now().strftime('%Y-%m-%d')
    base_dir  = os.path.dirname(__file__)
    PORT      = 8787
    BASE_URL  = f'http://localhost:{PORT}'

    # Global browser digest
    browser_html = build_browser_html(articles, results)
    global_path  = os.path.join(base_dir, f'digest_{date_slug}.html')
    with open(global_path, 'w', encoding='utf-8') as f:
        f.write(browser_html)
    global_url = f'{BASE_URL}/digest_{date_slug}.html'
    print(f"Global digest saved: {global_path}")

    # Per-article HTML pages
    articles_dir = os.path.join(base_dir, 'articles')
    os.makedirs(articles_dir, exist_ok=True)
    article_idx = 0
    for article, result in zip(articles, results):
        if not result.get('summary'):
            continue
        article_idx += 1
        filename  = f'{date_slug}-{article_idx:03d}.html'
        page_path = os.path.join(articles_dir, filename)
        page_html = build_article_page(article, result['summary'], global_url)
        with open(page_path, 'w', encoding='utf-8') as f:
            f.write(page_html)
        article['page_url'] = f'{BASE_URL}/articles/{filename}'
    print(f"  {article_idx} article pages saved to articles/")

    # Start/restart local HTTP server (skip in CI — no display/Windows flags)
    if not os.getenv('CI'):
        _restart_server(base_dir, PORT)

    # Email — narratives + links
    email_html = build_email_html(articles, results, global_url)
    subject    = f"CRE News Digest \u2014 {today}"
    print(f"Sending digest to {RECIPIENT}...")
    status = send_digest(email_html, subject)
    print(f"Done. Status: {status}")


if __name__ == '__main__':
    main()
