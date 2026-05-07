"""External live-data integrations using real APIs.

Do not use LLM as a source of truth for current events or prices.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import re
from typing import Any, Callable

import requests

from app.core.config import settings


FetchResult = dict[str, Any]
_TOPIC_STOPWORDS = {
    "what", "whats", "what's", "is", "are", "the", "a", "an", "between", "about", "of", "on", "for",
    "show", "get", "give", "find", "tell", "me", "latest", "today", "current", "live", "news", "update", "updates",
}


def _safe_get(
    source: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int | None = None,
) -> FetchResult:
    req_timeout = timeout or settings.LIVE_API_TIMEOUT_SECONDS
    try:
        response = requests.get(url, params=params, headers=headers, timeout=req_timeout)
        response.raise_for_status()
        payload = response.json()
        return {
            "source": source,
            "ok": True,
            "status_code": response.status_code,
            "data": payload,
        }
    except requests.Timeout:
        return {
            "source": source,
            "ok": False,
            "error": "timeout",
            "message": f"Timed out after {req_timeout}s",
        }
    except requests.RequestException as exc:
        return {
            "source": source,
            "ok": False,
            "error": "request_error",
            "message": str(exc),
        }
    except ValueError as exc:
        return {
            "source": source,
            "ok": False,
            "error": "invalid_json",
            "message": str(exc),
        }


def _sports_events_today() -> FetchResult:
    return _safe_get(
        "sports_cricket_events",
        "https://www.thesportsdb.com/api/v1/json/3/eventsday.php",
        params={"d": datetime.now().date().isoformat(), "s": "Cricket"},
    )


def _weather_chennai() -> FetchResult:
    return _safe_get(
        "weather_open_meteo",
        "https://api.open-meteo.com/v1/forecast",
        params={"latitude": 13.08, "longitude": 80.27, "current_weather": "true"},
    )


# Common Indian + global cities with their lat/long. Used to short-circuit a
# geocoding call when a known name appears in the query (cheap + offline).
_CITY_COORDS: dict[str, tuple[float, float, str]] = {
    "chennai":       (13.0827, 80.2707, "Chennai"),
    "bangalore":     (12.9716, 77.5946, "Bangalore"),
    "bengaluru":     (12.9716, 77.5946, "Bengaluru"),
    "hyderabad":     (17.3850, 78.4867, "Hyderabad"),
    "mumbai":        (19.0760, 72.8777, "Mumbai"),
    "delhi":         (28.6139, 77.2090, "Delhi"),
    "new delhi":     (28.6139, 77.2090, "New Delhi"),
    "kolkata":       (22.5726, 88.3639, "Kolkata"),
    "pune":          (18.5204, 73.8567, "Pune"),
    "ahmedabad":     (23.0225, 72.5714, "Ahmedabad"),
    "jaipur":        (26.9124, 75.7873, "Jaipur"),
    "lucknow":       (26.8467, 80.9462, "Lucknow"),
    "visakhapatnam": (17.6868, 83.2185, "Visakhapatnam"),
    "vizag":         (17.6868, 83.2185, "Visakhapatnam"),
    "vijayawada":    (16.5062, 80.6480, "Vijayawada"),
    "tirupati":      (13.6288, 79.4192, "Tirupati"),
    "guntur":        (16.3067, 80.4365, "Guntur"),
    "kochi":         (9.9312, 76.2673, "Kochi"),
    "trivandrum":    (8.5241, 76.9366, "Thiruvananthapuram"),
    "coimbatore":    (11.0168, 76.9558, "Coimbatore"),
    "madurai":       (9.9252, 78.1198, "Madurai"),
    "noida":         (28.5355, 77.3910, "Noida"),
    "gurgaon":       (28.4595, 77.0266, "Gurgaon"),
    "gurugram":      (28.4595, 77.0266, "Gurugram"),
    "bhubaneswar":   (20.2961, 85.8245, "Bhubaneswar"),
    "patna":         (25.5941, 85.1376, "Patna"),
    "indore":        (22.7196, 75.8577, "Indore"),
    "nagpur":        (21.1458, 79.0882, "Nagpur"),
    "surat":         (21.1702, 72.8311, "Surat"),
    "london":        (51.5074, -0.1278, "London"),
    "new york":      (40.7128, -74.0060, "New York"),
    "tokyo":         (35.6762, 139.6503, "Tokyo"),
    "dubai":         (25.2048, 55.2708, "Dubai"),
    "singapore":     (1.3521, 103.8198, "Singapore"),
}

# Common typo / abbreviation map onto canonical keys above.
_CITY_ALIASES: dict[str, str] = {
    "vishakapatnam":   "visakhapatnam",
    "vishakhapatnam":  "visakhapatnam",
    "visakapatnam":    "visakhapatnam",
    "vizagcity":       "vizag",
    "blr":             "bangalore",
    "hyd":             "hyderabad",
    "mum":             "mumbai",
    "bombay":          "mumbai",
    "calcutta":        "kolkata",
    "madras":          "chennai",
}


def _resolve_city(query: str) -> tuple[float, float, str] | None:
    """Find a known city in the query, accounting for aliases and typos.

    Punctuation is stripped before matching so 'visakapatnam?' still resolves.
    """
    if not query:
        return None
    # Reuse the normaliser so 'Vizag,' / 'visakapatnam?' / extra spaces all work.
    q = " " + _normalize_query(query) + " "
    # Apply alias substitutions first
    for typo, canonical in _CITY_ALIASES.items():
        q = q.replace(f" {typo} ", f" {canonical} ")
    # Sort longest first so 'new delhi' wins over 'delhi'
    for city in sorted(_CITY_COORDS.keys(), key=len, reverse=True):
        if f" {city} " in q:
            return _CITY_COORDS[city]
    return None


# Stop-words excluded from candidate place-name extraction.
_PLACE_STOPWORDS = {
    "what", "whats", "is", "are", "the", "a", "an", "of", "in", "on", "at",
    "for", "to", "and", "or", "with", "current", "today", "now", "live",
    "weather", "wheather", "wether", "temperature", "rain", "rainfall", "climate",
    "forecast", "humidity", "please", "tell", "me", "give", "show", "get",
    "find", "how", "whats", "place", "city", "right", "like", "looking",
    "report", "condition", "conditions", "update", "details",
}


def _extract_place_candidate(query: str) -> str | None:
    """Pull out the most likely place name from a free-form weather query.

    'current weather in Visakhapatnam' -> 'Visakhapatnam'
    'rain in Kakinada today'           -> 'Kakinada'
    'weather'                          -> None
    """
    if not query:
        return None
    norm = _normalize_query(query)
    if not norm:
        return None

    # Prefer text after 'in '/'at '/'for ' which conventionally precedes a place.
    for marker in (" in ", " at ", " for "):
        idx = norm.find(marker)
        if idx >= 0:
            tail = norm[idx + len(marker):].strip()
            tokens = [t for t in tail.split() if t and t not in _PLACE_STOPWORDS]
            if tokens:
                # Take up to the first 3 tokens — covers 'new delhi', 'navi mumbai'.
                return " ".join(tokens[:3])

    # Fallback: any non-stopword token, longest first.
    tokens = [t for t in norm.split() if t and t not in _PLACE_STOPWORDS and len(t) > 2]
    if not tokens:
        return None
    # Take the last 1–2 tokens (queries usually end with the place).
    return " ".join(tokens[-2:]) if len(tokens) >= 2 else tokens[-1]


def _geocode_open_meteo(place: str) -> tuple[float, float, str] | None:
    """Resolve any place name to (lat, lon, display) via Open-Meteo's free
    geocoding API. Returns None on any failure.

    Docs: https://open-meteo.com/en/docs/geocoding-api
    """
    if not place:
        return None
    try:
        result = _safe_get(
            "open_meteo_geocode",
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": place, "count": 1, "language": "en", "format": "json"},
            timeout=8,
        )
        if not result.get("ok"):
            return None
        data = result.get("data") or {}
        candidates = data.get("results") or []
        if not candidates:
            return None
        top = candidates[0]
        lat = top.get("latitude")
        lon = top.get("longitude")
        if lat is None or lon is None:
            return None
        # Build a clean display name: 'City, Admin1, Country'
        parts = [p for p in [top.get("name"), top.get("admin1"), top.get("country")] if p]
        # Avoid duplicate words ('Visakhapatnam, Andhra Pradesh, India')
        seen: set[str] = set()
        display_parts = []
        for p in parts:
            key = p.lower()
            if key in seen:
                continue
            seen.add(key)
            display_parts.append(p)
        display = ", ".join(display_parts) or place.title()
        return (float(lat), float(lon), display)
    except Exception:
        return None


def _weather_for_query(query: str) -> FetchResult:
    """Fetch current weather for the city named in the query.

    Resolution order:
        1. Static lookup (`_resolve_city`) — fast, offline, covers ~30 known cities.
        2. Open-Meteo geocoding API — handles ANY place worldwide.
        3. Fallback to Chennai if nothing matches and no place was extractable.

    The chosen display name is attached to `data.location_name` for the formatter.
    Adds richer fields (`hourly`/`daily`) per Open-Meteo docs so consumers can
    render humidity, precipitation chance, min/max temperature etc.
    """
    coords = _resolve_city(query)
    used_geocoder = False

    if coords is None:
        place = _extract_place_candidate(query)
        if place:
            geo = _geocode_open_meteo(place)
            if geo is not None:
                coords = geo
                used_geocoder = True

    if coords is None:
        # No place mentioned at all — fall back to Chennai default.
        coords = _CITY_COORDS["chennai"]

    lat, lon, display = coords
    result = _safe_get(
        "weather_open_meteo",
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true",
            # Extras — see https://open-meteo.com/en/docs
            "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": 3,
        },
    )
    # Augment the response with the resolved location for the formatter.
    if result.get("ok") and isinstance(result.get("data"), dict):
        result["data"]["location_name"] = display
        result["data"]["resolved_via"] = "geocode" if used_geocoder else "static"
        result["data"]["latitude_used"] = lat
        result["data"]["longitude_used"] = lon
    return result


def _bitcoin_price() -> FetchResult:
    return _safe_get(
        "crypto_coingecko",
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": "bitcoin", "vs_currencies": "usd"},
    )


def _ip_geolocation() -> FetchResult:
    return _safe_get("ip_geo", "http://ip-api.com/json/")


def _inshorts_tech_news() -> FetchResult:
    return _safe_get(
        "news_inshorts_tech",
        "https://inshorts.deta.dev/news",
        params={"category": "technology"},
    )


def _yahoo_reliance() -> FetchResult:
    return _safe_get(
        "finance_reliance_yahoo",
        "https://query1.finance.yahoo.com/v8/finance/chart/RELIANCE.NS",
        params={"interval": "1d", "range": "1mo"},
    )


def _mutual_fund_master() -> FetchResult:
    return _safe_get("mutual_fund_master", "https://api.mfapi.in/mf")


def _newsapi_business_india() -> FetchResult:
    if not settings.NEWSAPI_KEY:
        return {
            "source": "newsapi_business_india",
            "ok": False,
            "error": "missing_api_key",
            "message": "NEWSAPI_KEY is not set",
        }
    return _safe_get(
        "newsapi_business_india",
        "https://newsapi.org/v2/top-headlines",
        params={"country": "in", "category": "business", "apiKey": settings.NEWSAPI_KEY},
    )


def _country_india() -> FetchResult:
    return _safe_get("country_india", "https://restcountries.com/v3.1/name/india")


def _cricapi_current_matches() -> FetchResult:
    if not settings.CRICAPI_KEY:
        return {
            "source": "cricapi_current_matches",
            "ok": False,
            "error": "missing_api_key",
            "message": "CRICAPI_KEY is not set",
        }
    return _safe_get(
        "cricapi_current_matches",
        "https://api.cricapi.com/v1/currentMatches",
        params={"apikey": settings.CRICAPI_KEY, "offset": 0},
    )


def _thenews_top_india() -> FetchResult:
    if not settings.THENEWSAPI_TOKEN:
        return {
            "source": "thenewsapi_top_india",
            "ok": False,
            "error": "missing_api_key",
            "message": "THENEWSAPI_TOKEN is not set",
        }
    return _safe_get(
        "thenewsapi_top_india",
        "https://api.thenewsapi.com/v1/news/top",
        params={"api_token": settings.THENEWSAPI_TOKEN, "locale": "in", "language": "en"},
    )


def _thenews_business_india() -> FetchResult:
    if not settings.THENEWSAPI_TOKEN:
        return {
            "source": "thenewsapi_business_india",
            "ok": False,
            "error": "missing_api_key",
            "message": "THENEWSAPI_TOKEN is not set",
        }
    return _safe_get(
        "thenewsapi_business_india",
        "https://api.thenewsapi.com/v1/news/top",
        params={
            "api_token": settings.THENEWSAPI_TOKEN,
            "locale": "in",
            "categories": "business",
            "language": "en",
        },
    )


def _thenews_search_mutual_fund() -> FetchResult:
    if not settings.THENEWSAPI_TOKEN:
        return {
            "source": "thenewsapi_mutual_fund_search",
            "ok": False,
            "error": "missing_api_key",
            "message": "THENEWSAPI_TOKEN is not set",
        }
    return _safe_get(
        "thenewsapi_mutual_fund_search",
        "https://api.thenewsapi.com/v1/news/all",
        params={
            "api_token": settings.THENEWSAPI_TOKEN,
            "search": "mutual fund india",
            "language": "en",
            "limit": 5,
        },
    )


def _thenews_topic_search(topic: str) -> FetchResult:
    if not settings.THENEWSAPI_TOKEN:
        return {
            "source": "thenewsapi_topic_search",
            "ok": False,
            "error": "missing_api_key",
            "message": "THENEWSAPI_TOKEN is not set",
        }
    return _safe_get(
        "thenewsapi_topic_search",
        "https://api.thenewsapi.com/v1/news/all",
        params={
            "api_token": settings.THENEWSAPI_TOKEN,
            "search": topic,
            "language": "en",
            "limit": 8,
        },
    )


def _topic_from_query(query: str) -> str | None:
    words = re.findall(r"[a-zA-Z0-9]+", query.lower())
    filtered = [w for w in words if w not in _TOPIC_STOPWORDS and len(w) > 1]
    if not filtered:
        return None
    return " ".join(filtered[:6]).strip() or None


def _thenews_tech_finance_india() -> FetchResult:
    if not settings.THENEWSAPI_TOKEN:
        return {
            "source": "thenewsapi_tech_finance_india",
            "ok": False,
            "error": "missing_api_key",
            "message": "THENEWSAPI_TOKEN is not set",
        }
    return _safe_get(
        "thenewsapi_tech_finance_india",
        "https://api.thenewsapi.com/v1/news/top",
        params={
            "api_token": settings.THENEWSAPI_TOKEN,
            "categories": "tech,business",
            "locale": "in",
            "language": "en",
        },
    )


def _rss_the_hindu() -> FetchResult:
    """The Hindu — Top Stories via RSS-to-JSON converter."""
    return _safe_get(
        "rss_the_hindu_news",
        "https://api.rss2json.com/v1/api.json",
        params={"rss_url": "https://www.thehindu.com/feeder/default.rss"},
    )


def _rss_economic_times() -> FetchResult:
    """Economic Times — Markets via RSS-to-JSON converter."""
    return _safe_get(
        "rss_economic_times_markets",
        "https://api.rss2json.com/v1/api.json",
        params={"rss_url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"},
    )


def _rss_moneycontrol() -> FetchResult:
    """Moneycontrol — Finance via RSS-to-JSON converter."""
    return _safe_get(
        "rss_moneycontrol_finance",
        "https://api.rss2json.com/v1/api.json",
        params={"rss_url": "https://www.moneycontrol.com/rss/latestnews.xml"},
    )


def _rss_ndtv() -> FetchResult:
    """NDTV — India News via RSS-to-JSON converter."""
    return _safe_get(
        "rss_ndtv_india_news",
        "https://api.rss2json.com/v1/api.json",
        params={"rss_url": "https://feeds.feedburner.com/ndtvnews-india-newscl"},
    )


def _all_sources() -> dict[str, Callable[[], FetchResult]]:
    return {
        "sports_cricket_events": _sports_events_today,
        "weather_open_meteo": _weather_chennai,
        "crypto_coingecko": _bitcoin_price,
        "ip_geo": _ip_geolocation,
        "news_inshorts_tech": _inshorts_tech_news,
        "finance_reliance_yahoo": _yahoo_reliance,
        "mutual_fund_master": _mutual_fund_master,
        "newsapi_business_india": _newsapi_business_india,
        "country_india": _country_india,
        "cricapi_current_matches": _cricapi_current_matches,
        "thenewsapi_top_india": _thenews_top_india,
        "thenewsapi_business_india": _thenews_business_india,
        "thenewsapi_mutual_fund_search": _thenews_search_mutual_fund,
        "thenewsapi_tech_finance_india": _thenews_tech_finance_india,
        "rss_the_hindu_news": _rss_the_hindu,
        "rss_economic_times_markets": _rss_economic_times,
        "rss_moneycontrol_finance": _rss_moneycontrol,
        "rss_ndtv_india_news": _rss_ndtv,
    }


def _select_sources(query: str) -> dict[str, Callable[[], FetchResult]]:
    q = query.lower()
    all_map = _all_sources()

    selected: set[str] = {"ip_geo"}
    domain_selected = False

    if any(token in q for token in ["sport", "cricket", "match"]):
        selected.update({"sports_cricket_events", "cricapi_current_matches"})
        domain_selected = True
    if any(token in q for token in ["weather", "temperature", "rain", "climate"]):
        selected.add("weather_open_meteo")
        domain_selected = True
    if any(token in q for token in ["crypto", "bitcoin", "coin"]):
        selected.add("crypto_coingecko")
        domain_selected = True
    if any(token in q for token in ["stock", "share", "reliance", "finance", "market"]):
        selected.update({"finance_reliance_yahoo", "mutual_fund_master", "rss_economic_times_markets", "rss_moneycontrol_finance"})
        domain_selected = True
    if any(token in q for token in ["news", "headline", "technology", "business", "latest"]):
        selected.update(
            {
                "news_inshorts_tech",
                "newsapi_business_india",
                "thenewsapi_top_india",
                "thenewsapi_business_india",
                "thenewsapi_tech_finance_india",
                "rss_the_hindu_news",
                "rss_economic_times_markets",
                "rss_moneycontrol_finance",
                "rss_ndtv_india_news",
            }
        )
        domain_selected = True
    if any(token in q for token in ["war", "conflict", "iran", "usa", "world", "geopolitics", "politics", "topic", "update"]):
        selected.update({"thenewsapi_top_india", "rss_the_hindu_news", "rss_ndtv_india_news"})
        domain_selected = True
    if any(token in q for token in ["mutual fund", "fund"]):
        selected.update({"mutual_fund_master", "thenewsapi_mutual_fund_search"})
        domain_selected = True
    if any(token in q for token in ["india", "country"]):
        selected.update({"country_india", "rss_ndtv_india_news"})
        domain_selected = True

    # For generic live/current queries with no domain hints, run a balanced core set.
    if any(token in q for token in ["live", "today", "current", "latest"]):
        if not domain_selected:
            selected.update(
                {
                    "sports_cricket_events",
                    "weather_open_meteo",
                    "crypto_coingecko",
                    "news_inshorts_tech",
                    "rss_the_hindu_news",
                }
            )

    return {name: all_map[name] for name in selected if name in all_map}


def get_live_data(query: str) -> dict[str, Any]:
    """Fetch live data from real APIs and return normalized JSON payload."""
    selected = _select_sources(query)

    q = query.lower()
    topic = _topic_from_query(query)
    if topic and any(token in q for token in ["news", "headline", "latest", "today", "current", "live", "war", "update", "topic", "iran", "usa"]):
        selected["thenewsapi_topic_search"] = (lambda t=topic: _thenews_topic_search(t))

    # When weather is selected, swap the static Chennai fetcher for a query-aware
    # one that resolves the city named in the question (e.g. Visakhapatnam, Vizag).
    if "weather_open_meteo" in selected:
        selected["weather_open_meteo"] = (lambda qq=query: _weather_for_query(qq))

    sources: dict[str, FetchResult] = {}
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(selected)))) as pool:
        future_to_name = {pool.submit(fetcher): name for name, fetcher in selected.items()}
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                sources[name] = future.result()
            except Exception as exc:
                sources[name] = {
                    "source": name,
                    "ok": False,
                    "error": "unexpected_error",
                    "message": str(exc),
                }

    successful = [item for item in sources.values() if item.get("ok")]
    errors = [item for item in sources.values() if not item.get("ok")]

    return {
        "query": query,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_count": len(sources),
        "success_count": len(successful),
        "error_count": len(errors),
        "has_data": len(successful) > 0,
        "sources": sources,
        "errors": errors,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Multi-intent helpers — explicit detect → targeted fetch → category-grouped data.
# Wraps existing single-API fetchers; does not alter get_live_data behaviour.
# ─────────────────────────────────────────────────────────────────────────────

# Each intent maps to one or more underlying source fetchers (already defined above).
_INTENT_TO_SOURCES: dict[str, list[str]] = {
    "crypto":      ["crypto_coingecko"],
    "weather":     ["weather_open_meteo"],
    "stocks":      ["finance_reliance_yahoo", "rss_economic_times_markets", "rss_moneycontrol_finance"],
    "mutual_fund": ["mutual_fund_master", "thenewsapi_mutual_fund_search"],
    "sports":      ["sports_cricket_events", "cricapi_current_matches"],
    "news":        ["rss_the_hindu_news", "rss_ndtv_india_news", "thenewsapi_top_india", "news_inshorts_tech"],
}

_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    # Plain substring matches against the lowercased + space-normalised query.
    # Include common typos and spaced variants ("head lines", "wheather") so noisy
    # user input still routes to the right intent.
    "crypto":      ("crypto", "bitcoin", "ethereum", "btc", "eth", "coin"),
    "weather":     (
        "weather", "wheather", "wether", "temperature", "rain", "climate",
        "forecast", "humidity", "rainfall",
    ),
    "stocks":      (
        "stock", "stocks", "share price", "shares", "reliance", "nifty",
        "sensex", "tcs", "infy", "market", "sharemarket", "stockmarket",
    ),
    "mutual_fund": ("mutual fund", "mutualfund", "mf nav", "nav"),
    "sports":      ("cricket", "ipl", "match", "score", "scorecard"),
    "news":        (
        "news", "headline", "headlines", "head line", "head lines", "headlne",
        "breaking", "topic", "war", "conflict", "iran", "usa", "top stories",
        "current affairs",
    ),
}


def _normalize_query(query: str) -> str:
    """Lowercase, strip punctuation to spaces, collapse whitespace.

    'Top head-lines today?, current wheather!' -> 'top head lines today current wheather'
    A second variant with all spaces removed is also produced so 'sharemarket'
    still matches 'share market' style keywords.
    """
    import re
    q = (query or "").lower()
    q = re.sub(r"[^a-z0-9]+", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


def detect_multiple_intents(query: str) -> list[str]:
    """Detect every relevant intent in the query (multi-label).

    Returns a list of intent keys (e.g. ['crypto', 'weather', 'news']) preserving
    a stable preferred display order. Tolerates punctuation, extra spacing and
    common typos.

    Matching rules (avoid false positives like 'eth' inside 'are the'):
    - Single-word keyword → match as a WHOLE WORD against the normalised query.
    - Multi-word keyword (contains a space) → match either as a contiguous
      phrase in the normalised query OR as a single concatenated token in the
      space-removed variant (handles 'share price' vs 'sharemarket').
    """
    if not query:
        return []
    q = _normalize_query(query)
    if not q:
        return []
    q_padded = " " + q + " "
    q_nospace = q.replace(" ", "")
    order = ["crypto", "weather", "stocks", "mutual_fund", "sports", "news"]
    detected: list[str] = []
    for intent in order:
        for kw in _INTENT_KEYWORDS[intent]:
            kw_l = kw.lower().strip()
            if not kw_l:
                continue
            if " " in kw_l:
                # Multi-word keyword: phrase match OR concatenated token match.
                if kw_l in q or kw_l.replace(" ", "") in q_nospace:
                    detected.append(intent)
                    break
            else:
                # Single-word keyword: require whole-word match.
                if f" {kw_l} " in q_padded:
                    detected.append(intent)
                    break
    return detected


def _fetch_intent(intent: str, query: str) -> dict[str, FetchResult]:
    """Fetch all underlying sources for a single intent in parallel."""
    source_names = _INTENT_TO_SOURCES.get(intent, [])
    all_map = _all_sources()
    fetchers: dict[str, Callable[[], FetchResult]] = {
        name: all_map[name] for name in source_names if name in all_map
    }

    # For news intent, also include a topic-targeted search to capture "Iran USA war" etc.
    if intent == "news":
        topic = _topic_from_query(query)
        if topic:
            fetchers["thenewsapi_topic_search"] = (lambda t=topic: _thenews_topic_search(t))

    # For weather, swap the static Chennai fetcher for a query-aware one that
    # resolves the city mentioned in the user question (e.g. "Visakhapatnam").
    if intent == "weather":
        fetchers["weather_open_meteo"] = (lambda q=query: _weather_for_query(q))

    if not fetchers:
        return {}

    results: dict[str, FetchResult] = {}
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(fetchers)))) as pool:
        future_to_name = {pool.submit(f): n for n, f in fetchers.items()}
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                results[name] = {
                    "source": name,
                    "ok": False,
                    "error": "unexpected_error",
                    "message": str(exc),
                }
    return results


def get_multi_intent_data(query: str) -> dict[str, Any]:
    """Detect multiple intents and fetch ONLY what each intent needs, grouped per category.

    Output shape:
        {
          "query": ...,
          "generated_at": iso8601,
          "intents": ["crypto", "weather", "news"],
          "categories": {
              "crypto":  {"sources": {...}, "ok_count": 1},
              "weather": {"sources": {...}, "ok_count": 1},
              "news":    {"sources": {...}, "ok_count": 3},
          },
          "has_data": bool,
          # Backward-compatible flattened view for existing summarisers:
          "sources": {<source_name>: <FetchResult>, ...},
          "success_count": int,
        }
    """
    intents = detect_multiple_intents(query)
    categories: dict[str, dict[str, Any]] = {}
    flat_sources: dict[str, FetchResult] = {}

    # Fetch each intent's sources in parallel across intents.
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(intents) or 1))) as pool:
        future_to_intent = {pool.submit(_fetch_intent, intent, query): intent for intent in intents}
        for future in as_completed(future_to_intent):
            intent = future_to_intent[future]
            try:
                results = future.result()
            except Exception as exc:
                results = {"_error": {"source": intent, "ok": False, "error": "unexpected_error", "message": str(exc)}}

            ok_count = sum(1 for r in results.values() if isinstance(r, dict) and r.get("ok"))
            categories[intent] = {"sources": results, "ok_count": ok_count}
            for name, payload in results.items():
                flat_sources[name] = payload

    success_count = sum(1 for r in flat_sources.values() if isinstance(r, dict) and r.get("ok"))
    return {
        "query": query,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "intents": intents,
        "categories": categories,
        "sources": flat_sources,
        "source_count": len(flat_sources),
        "success_count": success_count,
        "error_count": len(flat_sources) - success_count,
        "has_data": success_count > 0,
    }

