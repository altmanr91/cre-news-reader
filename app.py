import streamlit as st
from rss_fetcher import fetch_articles
from summarizer import get_summary
from article_scraper import get_full_article_text
from geocoder import inject_geocoded_address
from calculator import inject_calculated_metrics
from filter import get_title_filter_reason, get_summary_filter_reason
from models import ArticleSummary
from datetime import datetime
import json
import os
import urllib.parse

DEV_MODE = True
DEV_ARTICLES_PATH = os.path.join(os.path.dirname(__file__), 'dev_articles.json')

st.set_page_config(page_title="CRE News Reader", layout="wide")
st.title("CRE News Reader")
st.markdown("---")


def _fmt_dollars(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.2f}B".rstrip('0').rstrip('.')
    if value >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:,.0f}K"
    return f"${value:,.0f}"


def _bold(text):
    st.markdown(f'**{text}**')


def _bullet(text):
    st.markdown(
        f'<p style="font-size:0.85em; margin:0.08em 0; padding-left:0.5em;">{text}</p>',
        unsafe_allow_html=True
    )


def _footnote(text):
    st.markdown(
        f'<p style="font-size:0.8em; font-style:italic; margin:0.3em 0;">{text}</p>',
        unsafe_allow_html=True
    )


def display_summary(summary: ArticleSummary):
    is_promotion = (summary.transaction_type or '').lower() == 'promotion'
    is_market = bool(summary.article_type) and not summary.transaction_type

    # Narrative
    if summary.narrative:
        st.markdown(summary.narrative.replace('$', r'\$'))

    if is_promotion:
        return

    # Type + Market
    if summary.transaction_type:
        _bold(f'TRANSACTION TYPE: {summary.transaction_type}')
    elif summary.article_type:
        _bold(f'ARTICLE TYPE: {summary.article_type}')

    if summary.market and not is_market:
        _bold(f'MARKET: {summary.market}')

    # DATA POINTS
    dp = summary.data_points
    if dp and not is_market:
        _bold('DATA POINTS:')
        if dp.property_type:
            _bullet(f'- Property Type: {dp.property_type}')
        if dp.property_name:
            _bullet(f'- Property Name: {dp.property_name}')
        if dp.address:
            maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(dp.address)}"
            addr_display = f'- Address: <a href="{maps_url}" target="_blank">{dp.address}</a>'
            if dp.address_sourced_separately:
                addr_display += '*'
            _bullet(addr_display)
        if dp.size_sf:
            _bullet(f'- Size: {dp.size_sf:,.0f} SF')
        if dp.size_units:
            _bullet(f'- Size: {dp.size_units:,} units')
        if dp.size_beds:
            _bullet(f'- Beds: {dp.size_beds:,}')
        if dp.size_keys:
            _bullet(f'- Keys: {dp.size_keys:,}')
        if dp.sale_price:
            _bullet(f'- Sale Price: {_fmt_dollars(dp.sale_price)}')
        if dp.loan_amount:
            _bullet(f'- Loan Amount: {_fmt_dollars(dp.loan_amount)}')
        if dp.total_project_cost:
            _bullet(f'- Total Project Cost: {_fmt_dollars(dp.total_project_cost)}')

        # Calculated metrics
        metrics = inject_calculated_metrics(summary)
        for label, value in metrics.items():
            _bullet(f'- {label}: {value}')

        if dp.occupancy is not None:
            tt = (summary.transaction_type or '').lower()
            if 'sale' in tt or 'acquisition' in tt:
                occ_label = 'Occupancy at Sale'
            elif 'loan' in tt or 'refinance' in tt:
                occ_label = 'Occupancy at Close'
            else:
                occ_label = 'Current Occupancy'
            _bullet(f'- {occ_label}: {dp.occupancy}%')
        if dp.year_built:
            _bullet(f'- Year Built: {dp.year_built}')
        if dp.completion:
            _bullet(f'- Completion: {dp.completion}')
        if dp.phase_1:
            _bullet(f'- Phase I: {dp.phase_1}')
        if dp.total_project_all_phases:
            _bullet(f'- Total Project (All Phases): {dp.total_project_all_phases}')
        if dp.original_plan:
            _bullet(f'- Original Plan: {dp.original_plan}')
        if dp.notable_features:
            _bullet(f'- Notable Features: {dp.notable_features}')
        if dp.project_notes:
            _bullet(f'- Project Notes: {dp.project_notes}')
        if dp.address_sourced_separately:
            _footnote('* Address sourced separately, not included in original article.')

    # KEY DATA POINTS (market articles)
    if summary.key_data_points and is_market:
        _bold('KEY DATA POINTS:')
        for kdp in summary.key_data_points:
            _bullet(f'- {kdp.label}: {kdp.value}')

    # COMPANIES/PEOPLE — deduplicate on first word of firm name to catch parent/subsidiary overlap
    if summary.companies_people and not is_market:
        _bold('COMPANIES/PEOPLE:')
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
                _bullet(f'- {entry.label}: {entry.firm_name} \u2014 {people_str}')
            else:
                _bullet(f'- {entry.label}: {entry.firm_name}')

    # TENANTS AT PROPERTY
    if summary.tenants:
        _bold('TENANTS AT PROPERTY:')
        for tenant in summary.tenants:
            _bullet(f'- {tenant}')

    # FINANCING
    if summary.financing:
        _bold('FINANCING:')
        st.markdown(summary.financing.replace('$', r'\$'))

    # SPONSOR PIPELINE — filter out non-CRE/lobbied projects
    _pipeline_skip = ['vanderbilt', 'university', 'satellite campus', 'lobbied', 'convinced']
    filtered_pipeline = [
        p for p in summary.sponsor_pipeline
        if not any(kw in (p.name_or_address + ' ' + p.description).lower() for kw in _pipeline_skip)
    ]
    if filtered_pipeline:
        _bold('SPONSOR PIPELINE:')
        for proj in filtered_pipeline:
            _bullet(f'- {proj.name_or_address}: {proj.description}')

    # MARKET INTELLIGENCE
    if summary.market_intelligence:
        _bold('MARKET INTELLIGENCE:')
        st.markdown(summary.market_intelligence.replace('$', r'\$'))


@st.cache_data(ttl=0)
def load_articles():
    if DEV_MODE and os.path.exists(DEV_ARTICLES_PATH):
        with open(DEV_ARTICLES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    articles = fetch_articles(max_articles_per_feed=2)
    for article in articles:
        full_text = get_full_article_text(article['link'])
        article['full_text'] = full_text
        article['has_full_text'] = full_text is not None
    if DEV_MODE:
        with open(DEV_ARTICLES_PATH, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
    return articles


with st.spinner("Fetching and analyzing latest CRE news..."):
    articles = load_articles()

st.markdown(f"### Latest News — {datetime.now().strftime('%B %d, %Y')}")
st.markdown(f"*{len(articles)} articles fetched from {len(set(a['source'] for a in articles))} sources*")
st.markdown("---")

for i, article in enumerate(articles):
    # Title-level pre-filter (no API call needed)
    pre_filter_reason = get_title_filter_reason(article['title'])
    if pre_filter_reason:
        with st.expander(f"**[{pre_filter_reason}]** {article['title']} — *{article['source']}*", expanded=False):
            st.markdown(f"[Read Full Article]({article['link']})")
        st.markdown("---")
        continue

    with st.container():
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"#### {article['title']}")
            st.markdown(f"*{article['source']} — {article['published']}*")
        with col2:
            st.markdown(f"[Read Full Article]({article['link']})")

        content = article['full_text'] if article['has_full_text'] else article['summary']
        try:
            summary = get_summary(article['title'], content, article.get('published'))
            summary = inject_geocoded_address(summary)

            post_filter_reason = get_summary_filter_reason(article, summary)
            if post_filter_reason:
                st.markdown(
                    f'<p style="color: gray; font-size: 0.85em; margin: 0;">'
                    f'Filtered: {post_filter_reason}</p>',
                    unsafe_allow_html=True
                )
            else:
                display_summary(summary)
        except Exception as e:
            st.error(f"Summary failed: {e}")

        if not article['has_full_text']:
            st.caption("Full article text unavailable — paywalled or restricted")

        st.markdown("---")
