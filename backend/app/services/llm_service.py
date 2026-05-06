"""LLM interaction helpers for live-data enriched responses."""

from __future__ import annotations

import json
from typing import Any

from app.ai.llm import get_llm_client, tracking_kwargs
from app.core.config import settings


def _tracking_without_user(test_type: str) -> dict[str, Any]:
    return {k: v for k, v in tracking_kwargs(test_type).items() if k != "user"}


def _compact_json(payload: dict[str, Any], limit: int = 24000) -> str:
    text = json.dumps(payload, ensure_ascii=True)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _clip_text(value: Any, max_len: int = 180) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _pick_relevant_source_names(query: str, source_names: list[str]) -> list[str]:
    q = query.lower()
    preferred: list[str] = []

    def add(name: str) -> None:
        if name in source_names and name not in preferred:
            preferred.append(name)

    if any(token in q for token in ["cricket", "match", "ipl", "score"]):
        add("sports_cricket_events")
        add("cricapi_current_matches")
    if any(token in q for token in ["bitcoin", "crypto", "coin"]):
        add("crypto_coingecko")
    if any(token in q for token in ["weather", "temperature", "rain", "climate"]):
        add("weather_open_meteo")
    if any(token in q for token in ["stock", "share", "reliance", "market", "finance"]):
        add("finance_reliance_yahoo")
        add("rss_economic_times_markets")
        add("rss_moneycontrol_finance")
    if any(token in q for token in ["news", "headline", "latest", "today"]):
        add("thenewsapi_topic_search")
        add("news_inshorts_tech")
        add("newsapi_business_india")
        add("thenewsapi_top_india")
        add("thenewsapi_business_india")
        add("rss_the_hindu_news")
        add("rss_ndtv_india_news")
    if any(token in q for token in ["war", "conflict", "iran", "usa", "topic", "update", "geopolitics", "politics"]):
        add("thenewsapi_topic_search")
        add("rss_the_hindu_news")
        add("rss_ndtv_india_news")

    if preferred:
        return preferred
    # Fallback: pass a small subset of successful sources.
    return source_names[:4]


def _summarize_source(source_name: str, payload: Any) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}

    if source_name == "crypto_coingecko":
        return {"bitcoin": data.get("bitcoin")}

    if source_name == "weather_open_meteo":
        return {"current_weather": data.get("current_weather")}

    if source_name == "sports_cricket_events":
        events = data.get("events") if isinstance(data.get("events"), list) else []
        slim = []
        for item in events[:8]:
            if not isinstance(item, dict):
                continue
            slim.append(
                {
                    "event": item.get("strEvent"),
                    "league": item.get("strLeague"),
                    "date": item.get("dateEvent") or item.get("strDate"),
                    "time": item.get("strTime"),
                    "status": item.get("strStatus"),
                }
            )
        return {"events": slim}

    if source_name == "cricapi_current_matches":
        matches = data.get("data") if isinstance(data.get("data"), list) else []
        slim = []
        for item in matches[:8]:
            if not isinstance(item, dict):
                continue
            slim.append(
                {
                    "name": item.get("name"),
                    "status": item.get("status"),
                    "dateTimeGMT": item.get("dateTimeGMT"),
                    "teams": item.get("teams"),
                }
            )
        return {"matches": slim}

    if source_name.startswith("rss_"):
        items = data.get("items") if isinstance(data.get("items"), list) else []
        slim = []
        for item in items[:10]:
            if not isinstance(item, dict):
                continue
            slim.append(
                {
                    "title": _clip_text(item.get("title"), 140),
                    "published": item.get("pubDate"),
                    "source": item.get("author") or data.get("feed", {}).get("title"),
                    "link": item.get("link"),
                }
            )
        return {"items": slim}

    if source_name in {"newsapi_business_india", "thenewsapi_top_india", "thenewsapi_business_india", "thenewsapi_tech_finance_india", "thenewsapi_topic_search", "news_inshorts_tech"}:
        key = "articles" if isinstance(data.get("articles"), list) else "data"
        items = data.get(key) if isinstance(data.get(key), list) else []
        slim = []
        for item in items[:10]:
            if not isinstance(item, dict):
                continue
            slim.append(
                {
                    "title": _clip_text(item.get("title"), 140),
                    "published": item.get("publishedAt") or item.get("published_at"),
                    "source": (item.get("source") or {}).get("name") if isinstance(item.get("source"), dict) else item.get("source"),
                    "link": item.get("url"),
                }
            )
        return {"items": slim}

    if source_name == "finance_reliance_yahoo":
        chart = data.get("chart") if isinstance(data.get("chart"), dict) else {}
        result = chart.get("result") if isinstance(chart.get("result"), list) and chart.get("result") else []
        if result and isinstance(result[0], dict):
            meta = result[0].get("meta") if isinstance(result[0].get("meta"), dict) else {}
            quote = (((result[0].get("indicators") or {}).get("quote") or [{}])[0] if isinstance((result[0].get("indicators") or {}).get("quote"), list) else {})
            closes = quote.get("close") if isinstance(quote.get("close"), list) else []
            closes = [c for c in closes if c is not None]
            return {
                "symbol": meta.get("symbol"),
                "currency": meta.get("currency"),
                "last_close": closes[-1] if closes else None,
                "recent_closes": closes[-5:] if closes else [],
            }
        return {}

    return data


def _prepare_live_context(query: str, data: dict[str, Any]) -> dict[str, Any]:
    sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
    successful = {name: payload for name, payload in sources.items() if isinstance(payload, dict) and payload.get("ok")}
    relevant_names = _pick_relevant_source_names(query, list(successful.keys()))

    focused: dict[str, Any] = {}
    for name in relevant_names:
        payload = successful.get(name)
        if not isinstance(payload, dict):
            continue
        focused[name] = {
            "status_code": payload.get("status_code"),
            "data": _summarize_source(name, payload.get("data")),
        }

    return {
        "query": data.get("query"),
        "generated_at": data.get("generated_at"),
        "success_count": data.get("success_count", 0),
        "focused_source_count": len(focused),
        "focused_sources": focused,
    }


def _deterministic_rescue(query: str, data: dict[str, Any]) -> str | None:
    q = query.lower()
    sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}

    if "bitcoin" in q or "crypto" in q:
        btc = ((sources.get("crypto_coingecko") or {}).get("data") or {}).get("bitcoin", {})
        usd = btc.get("usd") if isinstance(btc, dict) else None
        if usd is not None:
            return f"Current Bitcoin price: ${usd} USD (source: CoinGecko)."

    if "cricket" in q or "match" in q or "ipl" in q:
        events = ((sources.get("sports_cricket_events") or {}).get("data") or {}).get("events", [])
        if isinstance(events, list) and events:
            lines = []
            for item in events[:5]:
                if not isinstance(item, dict):
                    continue
                event = item.get("strEvent") or "Unknown match"
                date = item.get("dateEvent") or item.get("strDate") or ""
                time = item.get("strTime") or ""
                lines.append(f"- {event} {date} {time}".strip())
            if lines:
                return "Cricket matches today:\n" + "\n".join(lines)

    if any(token in q for token in ["news", "headline", "war", "iran", "usa", "update", "latest", "topic"]):
        topic_items = ((sources.get("thenewsapi_topic_search") or {}).get("data") or {}).get("data", [])
        if isinstance(topic_items, list) and topic_items:
            lines = []
            for item in topic_items[:5]:
                if not isinstance(item, dict):
                    continue
                title = item.get("title") or "Untitled"
                source = item.get("source") if isinstance(item.get("source"), str) else "TheNewsAPI"
                url = item.get("url") or ""
                lines.append(f"- {title} ({source}) {url}".strip())
            if lines:
                return "Latest topic-based news:\n" + "\n".join(lines)

    return None


def ask_llm(query: str, data: dict[str, Any], user_email: str, model: str | None = None) -> str:
    """Ask the model to filter, format, and interpret live API results intelligently."""
    chosen = model or settings.LLM_MODEL
    client = get_llm_client()

    system_prompt = (
        "You are a live-data assistant. Your task is to filter and extract ONLY the information "
        "the user asked for, using the provided API data as source-of-truth.\n"
        "Instructions:\n"
        "1. Parse the user query to understand exactly what they want (headlines, prices, scores, etc).\n"
        "2. Filter the API data to extract ONLY matching records.\n"
        "3. Format cleanly with bullet points or tables when there are multiple items.\n"
        "4. If data is not found, explicitly say 'No data found for: [user request]'.\n"
        "5. Return readable output with source attribution when applicable.\n"
        "6. For news/headlines: show title + short summary (2-3 lines max per item).\n"
        "7. For prices/numbers: show in clear format with units and timestamps.\n"
        "8. Never fabricate or assume data - only use what is provided."
    )

    focused_data = _prepare_live_context(query, data)

    user_prompt = (
        f"User Query (what they want):\n{query}\n\n"
        "Live API Data (filter and format from this only):\n"
        f"{_compact_json(focused_data, limit=12000)}\n\n"
        "Instructions:\n"
        "- Extract ONLY what matches the user query\n"
        "- Show top 5-10 results if multiple items\n"
        "- Use clear formatting (bullets, tables, or paragraphs)"
    )

    response = client.chat.completions.create(
        model=chosen,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=1200,
        user=user_email,
        **_tracking_without_user("live_data_filter_format"),
    )
    answer = (response.choices[0].message.content or "").strip()
    if "No data found for:" in answer:
        rescued = _deterministic_rescue(query, data)
        if rescued:
            return rescued
    return answer


def ask_llm_fallback(query: str, user_email: str, model: str | None = None) -> str:
    """Fallback generic LLM answer when APIs return no usable live data."""
    chosen = model or settings.LLM_MODEL
    client = get_llm_client()

    response = client.chat.completions.create(
        model=chosen,
        messages=[
            {
                "role": "system",
                "content": "Answer helpfully and clearly. If uncertain, say what additional data is needed.",
            },
            {"role": "user", "content": query},
        ],
        temperature=0.4,
        max_tokens=700,
        user=user_email,
        **_tracking_without_user("live_data_fallback"),
    )
    return (response.choices[0].message.content or "").strip()
