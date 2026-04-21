from models import ArticleSummary


def inject_calculated_metrics(summary: ArticleSummary) -> dict:
    """
    Compute per-unit / per-SF metrics from structured data.
    Returns a dict of {label: formatted_string} ready for display.
    No text parsing needed — all values are already typed numbers.
    """
    if not summary.data_points:
        return {}

    dp = summary.data_points
    tt = (summary.transaction_type or '').lower()
    is_development = any(t in tt for t in ('development', 'construction'))

    # Determine which price to calculate from
    price = None
    is_loan = False

    if dp.loan_amount:
        price = dp.loan_amount
        is_loan = True
    elif dp.total_project_cost:
        price = dp.total_project_cost
    elif dp.sale_price and not is_development:
        price = dp.sale_price

    if not price:
        return {}

    size_config = [
        ('size_sf',    'SF',   'SF'),
        ('size_units', 'Unit', 'unit'),
        ('size_beds',  'Bed',  'bed'),
        ('size_keys',  'Key',  'key'),
    ]

    active_sizes = [(attr, uc, ul) for attr, uc, ul in size_config if getattr(dp, attr, None)]
    n = len(active_sizes)

    if n == 0:
        return {}

    if n >= 3:
        return {}

    if n == 2:
        attrs = {a for a, _, _ in active_sizes}
        if 'size_sf' not in attrs:
            # Two unit-type fields (e.g. units + beds) — ambiguous, suppress
            return {}
        # SF + one unit type: decide based on property type and SF size
        prop_type = (dp.property_type or '').lower()
        is_mixed = 'mix' in prop_type or '/' in prop_type
        sf = dp.size_sf
        if is_mixed and sf >= 20000:
            # Multiple significant components — suppress all
            return {}
        if not is_mixed:
            # Single-use with two size metrics (e.g. self-storage: SF + units)
            # Calculate all — both metrics describe the same asset
            pass
        else:
            # Mixed-use with ancillary SF (<20k) — calculate unit types only, drop SF
            active_sizes = [(a, uc, ul) for a, uc, ul in active_sizes if a != 'size_sf']

    metrics = {}
    for attr, unit_cap, unit_lower in active_sizes:
        count = getattr(dp, attr, None)
        if not count or count <= 0:
            continue
        per = price / count
        if is_loan:
            label = f'Loan Per {unit_cap}'
        else:
            label = f'$/{unit_cap}'
        metrics[label] = f'${per:,.0f}/{unit_lower} (calculated)'

    return metrics
