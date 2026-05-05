import os
from pathlib import Path

from calculator import inject_calculated_metrics


def run_review(articles: list, results: list, date_slug: str) -> None:
    """
    Call Claude Haiku to review today's digest output for filter errors and data quality issues.
    Writes a structured markdown file to reviews/YYYY-MM-DD.md.
    Fails silently — a review error must never affect digest delivery.
    """
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("  [review] ANTHROPIC_API_KEY not set — skipping")
        return

    try:
        import anthropic
    except ImportError:
        print("  [review] anthropic package not installed — skipping")
        return

    kept_lines = []
    filtered_lines = []

    for article, result in zip(articles, results):
        title  = article.get('title', '(no title)')
        source = article.get('source', '')

        if result.get('filtered'):
            reason = result.get('filter_reason', 'Unknown')
            filtered_lines.append(f'- "{title}" | {source} | Filtered as: {reason}')
            continue

        if not result.get('summary'):
            continue

        summary = result['summary']
        tx = summary.transaction_type or ''
        at = summary.article_type or ''
        type_label = f'[{tx}]' if tx else f'[{at}]'
        market = summary.market or 'National'

        # Compact data points
        dp_parts = []
        if summary.data_points:
            dp = summary.data_points
            if dp.sale_price:
                dp_parts.append(f'${dp.sale_price / 1e6:.1f}M sale')
            if dp.loan_amount:
                dp_parts.append(f'${dp.loan_amount / 1e6:.1f}M loan')
            if dp.total_project_cost:
                dp_parts.append(f'${dp.total_project_cost / 1e6:.1f}M TPC')
            if dp.size_sf:
                dp_parts.append(f'{dp.size_sf:,.0f} SF')
            if dp.size_units:
                dp_parts.append(f'{dp.size_units} units')
            if dp.property_type:
                dp_parts.append(f'type:{dp.property_type}')

        # Include the first $/SF or $/unit metric so Claude can spot implausible values
        metrics = inject_calculated_metrics(summary)
        for label, val in metrics.items():
            if any(k in label for k in ('$/SF', '/unit', '/key', '/bed', '/acre')):
                dp_parts.append(f'{label}={val}')
                break

        # Companies — show all so hallucinations are visible
        cp_parts = []
        for entry in (summary.companies_people or []):
            people_str = '; '.join(p.name for p in (entry.people or []))
            cp_parts.append(
                f'{entry.label}:{entry.firm_name}'
                + (f'({people_str})' if people_str else '')
            )

        # Sponsor pipeline — show first 4 entries
        pipeline = [p[:80] for p in (summary.sponsor_pipeline or [])]

        line_parts = [f'- "{title}" | {source} | {type_label} | {market}']
        if dp_parts:
            line_parts.append(f'  Data: {" | ".join(dp_parts)}')
        if cp_parts:
            line_parts.append(f'  Companies: {", ".join(cp_parts)}')
        if pipeline:
            line_parts.append(f'  Pipeline: {"; ".join(pipeline[:4])}')

        kept_lines.append('\n'.join(line_parts))

    kept_text     = '\n'.join(kept_lines)     if kept_lines     else '(none)'
    filtered_text = '\n'.join(filtered_lines) if filtered_lines else '(none)'

    prompt = f"""You are reviewing a commercial real estate (CRE) news digest for quality issues.

The digest should contain: CRE transactions (sales, acquisitions, leases, loans, construction, development), CRE market research, and industry news directly relevant to CRE investors, lenders, and operators.

The digest should NOT contain: residential brokerage company M&A (e.g. one brokerage acquiring another brokerage), association board elections or governance announcements, pure political/campaign finance articles, articles where real estate is only incidental to a non-CRE story, or promotions at HVAC/MEP/trade contractor firms (they are not CRE principals).

Review the digest output below and identify problems in exactly these categories:

1. SHOULD HAVE BEEN FILTERED — kept articles that clearly do not belong (wrong classification, non-CRE content, corporate M&A of a non-real-estate business, etc.)
2. SHOULD HAVE APPEARED — filtered articles that are clearly relevant CRE content (e.g. significant lease suppressed due to extraction failure, REIT capital event filtered as non-CRE, CRE litigation filtered as non-CRE)
3. DATA QUALITY — kept articles with: (a) implausible $/SF or $/unit metrics for the property type and market; (b) companies_people entries that appear to be regulatory agencies, competitors, or contextual mentions mislabeled as transaction parties; (c) sponsor pipeline entries that are VC/PE portfolio companies rather than actual development projects

Be specific and actionable. Only flag genuine issues — do not nitpick minor imperfections.

Format your response EXACTLY as follows (omit any section with no issues):

## Review: {date_slug}

### Should Have Been Filtered
- "Title" — reason — Fix: specific prompt or filter rule change

### Should Have Appeared
- "Title" (filtered as: reason) — why it should appear — Fix: specific change

### Data Quality
- "Title" — specific issue — Fix: specific change

If no issues are found in any category, respond only with:

## Review: {date_slug}

No issues found.

---

KEPT ARTICLES ({len(kept_lines)} total):
{kept_text}

FILTERED ARTICLES ({len(filtered_lines)} total):
{filtered_text}"""

    print(f"  [review] Calling Claude Haiku ({len(kept_lines)} kept, {len(filtered_lines)} filtered)...")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=2000,
        messages=[{'role': 'user', 'content': prompt}],
    )
    review_text = response.content[0].text

    reviews_dir = Path('reviews')
    reviews_dir.mkdir(exist_ok=True)
    review_file = reviews_dir / f'{date_slug}.md'
    review_file.write_text(review_text, encoding='utf-8')
    print(f"  [review] Saved to {review_file}")
