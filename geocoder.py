import requests
import re
import os
from dotenv import load_dotenv
from models import ArticleSummary

load_dotenv()

_STATE_PATTERN = (
    r'(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|'
    r'MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|'
    r'Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|'
    r'Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|'
    r'Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|'
    r'New\s+Hampshire|New\s+Jersey|New\s+Mexico|New\s+York|North\s+Carolina|North\s+Dakota|'
    r'Ohio|Oklahoma|Oregon|Pennsylvania|Rhode\s+Island|South\s+Carolina|South\s+Dakota|'
    r'Tennessee|Texas|Utah|Vermont|Virginia|Washington|West\s+Virginia|Wisconsin|Wyoming)'
)
_ADDRESS_RE = re.compile(
    r'\d+[-\d]*\s+'
    r'(?:(?:NE|NW|SE|SW|[NSEWnsew])\.?\s+)?'
    r'[A-Za-z0-9][A-Za-z0-9\s\.\-]{2,40}'
    r'(?:Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr'
    r'|Road|Rd|Way|Lane|Ln|Court|Ct|Place|Pl'
    r'|Parkway|Pkwy|Highway|Hwy)\.?'
    r'(?:\s*,\s*|\s+)'
    r'[A-Za-z][A-Za-z\s]{1,29}'
    r',\s*' + _STATE_PATTERN,
    re.IGNORECASE
)


def _strip_phase_suffix(name):
    return re.sub(
        r'\s+(?:Phase|Stage|Building|Bldg|Tower|Block)\s+[IVXivx\d]+$',
        '', name, flags=re.IGNORECASE
    ).strip()


def _search_web_for_address(property_name, market):
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return None
    query = f'"{property_name}" {market} address'
    try:
        response = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": 5},
            timeout=7
        )
        data = response.json()
        texts = []
        for result in data.get("organic", []):
            texts.append(result.get("snippet", ""))
            texts.append(result.get("title", ""))
        for result in data.get("knowledgeGraph", {}).get("attributes", {}).values():
            texts.append(str(result))
        matches = []
        for text in texts:
            for match in _ADDRESS_RE.finditer(text):
                addr = match.group(0).strip()
                matches.append((addr.count(','), addr))
        if matches:
            matches.sort(reverse=True)
            return matches[0][1]
    except Exception:
        pass
    return None


def _confirm_with_google_maps(raw_address, market):
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return raw_address
    try:
        response = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": raw_address, "key": api_key},
            timeout=5
        )
        data = response.json()
        if data.get("status") == "OK" and data.get("results"):
            result = data["results"][0]
            formatted = result.get("formatted_address", "")
            market_city = market.split(",")[0].strip().lower()
            if market_city not in formatted.lower():
                return None
            parts = [p.strip() for p in formatted.split(",")]
            parts = [p for p in parts if p.upper() not in ("USA", "UNITED STATES")]
            if parts:
                parts[-1] = re.sub(r"\s+\d{5}(-\d{4})?$", "", parts[-1]).strip()
            if len(parts) >= 3:
                return ", ".join(parts)
    except Exception:
        pass
    return None


def get_property_address(property_name, market):
    raw = _search_web_for_address(property_name, market)
    if not raw:
        stripped = _strip_phase_suffix(property_name)
        if stripped != property_name:
            raw = _search_web_for_address(stripped, market)
    if not raw:
        return None
    return _confirm_with_google_maps(raw, market)


def _is_street_address(addr: str) -> bool:
    """Returns True only if addr begins with a building/street number."""
    return bool(re.match(r'^\d', addr.strip()))


def inject_geocoded_address(summary: ArticleSummary) -> ArticleSummary:
    """
    If the summary has no valid street address, attempt to look it up via Serper + Google Maps.
    Sets data_points.address and data_points.address_sourced_separately on the object.
    """
    if not summary.data_points:
        return summary

    # Skip only if a real street address (starts with a number) is already present
    if summary.data_points.address and _is_street_address(summary.data_points.address):
        return summary

    # Clear any non-address value the model may have set (e.g. just city/state)
    summary.data_points.address = None

    property_name = summary.data_points.property_name
    market = summary.market

    if not property_name or not market:
        return summary

    address = get_property_address(property_name, market)
    if not address:
        return summary

    summary.data_points.address = address
    summary.data_points.address_sourced_separately = True
    return summary
