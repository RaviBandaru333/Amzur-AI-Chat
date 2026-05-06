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
