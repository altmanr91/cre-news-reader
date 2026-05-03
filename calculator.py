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
    is_land = bool(dp.land_area_acres)

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

    # Multi-asset purchases: price spans multiple distinct buildings/parcels — $/SF is meaningless
    if dp.multi_asset_purchase:
        return {}

    size_config = [
        ('size_sf',    'SF',   'SF'),
        ('size_units', 'Unit', 'unit'),
        ('size_beds',  'Bed',  'bed'),
        ('size_keys',  'Key',  'key'),
    ]

    active_sizes = [(attr, uc, ul) for attr, uc, ul in size_config if getattr(dp, attr, None)]
    n = len(active_sizes)

    metrics = {}

    if n == 0:
        pass
    elif n >= 3:
        pass  # suppress — ambiguous multi-use
    elif n == 2:
        attrs = {a for a, _, _ in active_sizes}
        if 'size_sf' not in attrs:
            pass  # two unit-type fields — ambiguous, suppress
        else:
            prop_type = (dp.property_type or '').lower()
            is_mixed = 'mix' in prop_type or '/' in prop_type
            sf = dp.size_sf
            if is_mixed and sf >= 20000:
                pass  # multiple significant components — suppress all
            elif not is_mixed:
                # Single-use with two size metrics — calculate all
                for attr, unit_cap, unit_lower in active_sizes:
                    _add_metric(metrics, dp, attr, unit_cap, unit_lower, price, is_loan, is_land)
            else:
                # Mixed-use with ancillary SF (<20k) — unit types only
                for attr, unit_cap, unit_lower in active_sizes:
                    if attr != 'size_sf':
                        _add_metric(metrics, dp, attr, unit_cap, unit_lower, price, is_loan, is_land)
    else:
        for attr, unit_cap, unit_lower in active_sizes:
            _add_metric(metrics, dp, attr, unit_cap, unit_lower, price, is_loan, is_land)

    # Annual rent from rental rate × SF
    if dp.rental_rate and dp.size_sf:
        annual = dp.rental_rate * dp.size_sf
        metrics['Annual Rent'] = f'${annual:,.0f}/yr (calculated)'

    # Land area metrics — $/acre and $/land SF when site acreage is known.
    # Suppressed for built properties (year_built present) — acreage on existing buildings
    # is context, not a pricing basis.
    if is_land and dp.land_area_acres and price and not dp.year_built:
        acres = dp.land_area_acres
        per_acre    = price / acres
        per_land_sf = price / (acres * 43_560)
        prefix = 'Loan' if is_loan else '$'
        metrics[f'{prefix}/Acre']    = f'${per_acre:,.0f}/acre (calculated)'
        metrics[f'{prefix}/Land SF'] = f'${per_land_sf:,.2f}/land SF (calculated)'

    return metrics


def _add_metric(metrics: dict, dp, attr: str, unit_cap: str, unit_lower: str,
                price: float, is_loan: bool, is_land: bool) -> None:
    count = getattr(dp, attr, None)
    if not count or count <= 0:
        return
    per = price / count
    # For development land purchases, unit counts are buildable, not existing
    if attr == 'size_units' and is_land:
        uc_label = 'Buildable Unit'
        ul_label = 'buildable unit'
    else:
        uc_label = unit_cap
        ul_label = unit_lower
    label = f'Loan Per {uc_label}' if is_loan else f'$/{uc_label}'
    metrics[label] = f'${per:,.0f}/{ul_label} (calculated)'
