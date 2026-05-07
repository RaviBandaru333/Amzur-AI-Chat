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
        return {
            "current_weather": data.get("current_weather"),
            "location_name": data.get("location_name"),
            "daily": data.get("daily"),
            "hourly": data.get("hourly"),
        }

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


_CATEGORY_HEADINGS = {
    "crypto":      "📊 Crypto Price",
    "weather":     "🌦️ Weather",
    "stocks":      "📈 Stocks / Market",
    "mutual_fund": "💰 Mutual Funds",
    "sports":      "🏏 Sports / Cricket",
    "news":        "📰 Top Headlines",
}


def _first_ok(sources: dict[str, Any]) -> tuple[str, dict] | None:
    """Return (source_name, raw_data) for the first source that has ok=True."""
    if not isinstance(sources, dict):
        return None
    for name, payload in sources.items():
        if isinstance(payload, dict) and payload.get("ok"):
            return name, payload.get("data") or {}
    return None


def _section_crypto(sources: dict[str, Any]) -> str:
    found = _first_ok(sources)
    if not found:
        return "Data not available right now."
    _, raw = found
    btc = raw.get("bitcoin") if isinstance(raw, dict) else None
    if isinstance(btc, dict) and btc.get("usd") is not None:
        usd = btc["usd"]
        return f"Bitcoin is currently **${usd:,} USD**.\n- Source: CoinGecko"
    return "Data not available right now."


def _section_weather(sources: dict[str, Any], query: str) -> str:
    found = _first_ok(sources)
    if not found:
        return "Data not available right now."
    _, raw = found
    if not isinstance(raw, dict):
        return "Data not available right now."
    cw = raw.get("current_weather")
    if not isinstance(cw, dict):
        return "Data not available right now."
    location = raw.get("location_name") or "your area"
    temp = cw.get("temperature")
    wind = cw.get("windspeed")
    code = cw.get("weathercode")

    bits: list[str] = []
    if temp is not None:
        bits.append(f"**{temp}°C**")
    if wind is not None:
        bits.append(f"wind {wind} km/h")
    if code is not None:
        bits.append(f"code {code}")
    if not bits:
        return "Data not available right now."

    lines = [f"Current weather in **{location}**: " + ", ".join(bits)]

    # Daily min/max + precipitation total (when Open-Meteo extras are present).
    daily = raw.get("daily") if isinstance(raw, dict) else None
    if isinstance(daily, dict):
        tmax = (daily.get("temperature_2m_max") or [None])[0]
        tmin = (daily.get("temperature_2m_min") or [None])[0]
        precip = (daily.get("precipitation_sum") or [None])[0]
        extra = []
        if tmin is not None and tmax is not None:
            extra.append(f"today {tmin}°C – {tmax}°C")
        if precip is not None:
            extra.append(f"precipitation {precip} mm")
        if extra:
            lines.append("- " + ", ".join(extra))

    # Current-hour humidity + precipitation probability from the hourly array.
    hourly = raw.get("hourly") if isinstance(raw, dict) else None
    cw_time = cw.get("time")
    if isinstance(hourly, dict) and cw_time:
        times = hourly.get("time") or []
        try:
            idx = times.index(cw_time) if cw_time in times else 0
        except ValueError:
            idx = 0
        humidity_arr = hourly.get("relative_humidity_2m") or []
        precip_arr = hourly.get("precipitation_probability") or []
        humidity = humidity_arr[idx] if idx < len(humidity_arr) else None
        precip_prob = precip_arr[idx] if idx < len(precip_arr) else None
        extras = []
        if humidity is not None:
            extras.append(f"humidity {humidity}%")
        if precip_prob is not None:
            extras.append(f"rain chance {precip_prob}%")
        if extras:
            lines.append("- " + ", ".join(extras))

    lines.append("- Source: Open-Meteo")
    _ = query  # signature stable for future query-aware tweaks
    return "\n".join(lines)


def _section_stocks(sources: dict[str, Any]) -> str:
    # Try Yahoo Reliance first
    yh = sources.get("finance_reliance_yahoo")
    if isinstance(yh, dict) and yh.get("ok"):
        chart = (yh.get("data") or {}).get("chart") or {}
        result = chart.get("result") or []
        if result and isinstance(result[0], dict):
            meta = result[0].get("meta") or {}
            symbol = meta.get("symbol", "RELIANCE.NS")
            currency = meta.get("currency", "INR")
            price = meta.get("regularMarketPrice")
            if price is not None:
                return f"**{symbol}**: {price} {currency}\n- Source: Yahoo Finance"
    # Fallback to RSS markets
    for key in ("rss_economic_times_markets", "rss_moneycontrol_finance"):
        feed = sources.get(key)
        if isinstance(feed, dict) and feed.get("ok"):
            items = (feed.get("data") or {}).get("items") or []
            if items:
                titles = [i.get("title") for i in items[:3] if isinstance(i, dict) and i.get("title")]
                if titles:
                    label = "Economic Times" if "economic" in key else "Moneycontrol"
                    bullets = "\n".join(f"- {t}" for t in titles)
                    return f"Latest market headlines:\n{bullets}\n- Source: {label}"
    return "Data not available right now."


def _section_mutual_fund(sources: dict[str, Any]) -> str:
    mf = sources.get("mutual_fund_master")
    if isinstance(mf, dict) and mf.get("ok"):
        data = mf.get("data") or []
        if isinstance(data, list) and data:
            return f"Mutual fund master list available — **{len(data)}** schemes indexed.\n- Source: mfapi.in"
    nf = sources.get("thenewsapi_mutual_fund_search")
    if isinstance(nf, dict) and nf.get("ok"):
        items = (nf.get("data") or {}).get("data") or []
        if items:
            titles = [i.get("title") for i in items[:3] if isinstance(i, dict)]
            if titles:
                return "Recent mutual fund news:\n" + "\n".join(f"- {t}" for t in titles) + "\n- Source: TheNewsAPI"
    return "Data not available right now."


def _section_sports(sources: dict[str, Any]) -> str:
    ev = sources.get("sports_cricket_events")
    if isinstance(ev, dict) and ev.get("ok"):
        events = (ev.get("data") or {}).get("events") or []
        if isinstance(events, list) and events:
            lines = []
            for item in events[:5]:
                if not isinstance(item, dict):
                    continue
                title = item.get("strEvent") or "Match"
                date = item.get("dateEvent") or ""
                time = item.get("strTime") or ""
                status = item.get("strStatus") or ""
                lines.append(f"- {title} {date} {time} {status}".strip())
            if lines:
                return "Today's cricket matches:\n" + "\n".join(lines) + "\n- Source: TheSportsDB"
    cm = sources.get("cricapi_current_matches")
    if isinstance(cm, dict) and cm.get("ok"):
        items = (cm.get("data") or {}).get("data") or []
        if isinstance(items, list) and items:
            lines = []
            for item in items[:5]:
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or "Match"
                status = item.get("status") or ""
                lines.append(f"- {name} — {status}".strip(" —"))
            if lines:
                return "Current matches:\n" + "\n".join(lines) + "\n- Source: CricAPI"
    return "Data not available right now."


def _section_news(sources: dict[str, Any]) -> str:
    """Aggregate up to 5 headlines across all news sources, deduped by title."""
    seen_titles: set[str] = set()
    bullets: list[str] = []

    def add_items(items: list, source_label: str) -> None:
        for item in items:
            if len(bullets) >= 5:
                return
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            if not title or title.lower() in seen_titles:
                continue
            seen_titles.add(title.lower())
            bullets.append(f"{len(bullets) + 1}. {title} — *{source_label}*")

    # Topic search first (most relevant to user query)
    ts = sources.get("thenewsapi_topic_search")
    if isinstance(ts, dict) and ts.get("ok"):
        add_items((ts.get("data") or {}).get("data") or [], "TheNewsAPI search")

    # Then RSS feeds
    for key, label in [
        ("rss_the_hindu_news", "The Hindu"),
        ("rss_ndtv_india_news", "NDTV"),
        ("rss_economic_times_markets", "Economic Times"),
        ("rss_moneycontrol_finance", "Moneycontrol"),
    ]:
        feed = sources.get(key)
        if isinstance(feed, dict) and feed.get("ok"):
            add_items((feed.get("data") or {}).get("items") or [], label)

    # Then TheNewsAPI top stories
    for key, label in [
        ("thenewsapi_top_india", "TheNewsAPI India"),
        ("thenewsapi_business_india", "TheNewsAPI Business"),
        ("thenewsapi_tech_finance_india", "TheNewsAPI Tech/Finance"),
    ]:
        feed = sources.get(key)
        if isinstance(feed, dict) and feed.get("ok"):
            add_items((feed.get("data") or {}).get("data") or [], label)

    # Inshorts as fallback
    ish = sources.get("news_inshorts_tech")
    if isinstance(ish, dict) and ish.get("ok"):
        add_items((ish.get("data") or {}).get("data") or [], "Inshorts Tech")

    if not bullets:
        return "Data not available right now."
    return "\n".join(bullets)


_SECTION_BUILDERS = {
    "crypto":      lambda srcs, q: _section_crypto(srcs),
    "weather":     lambda srcs, q: _section_weather(srcs, q),
    "stocks":      lambda srcs, q: _section_stocks(srcs),
    "mutual_fund": lambda srcs, q: _section_mutual_fund(srcs),
    "sports":      lambda srcs, q: _section_sports(srcs),
    "news":        lambda srcs, q: _section_news(srcs),
}


def ask_llm_multi_intent(
    query: str,
    multi_data: dict[str, Any],
    user_email: str,
    model: str | None = None,
) -> str:
    """Deterministic multi-section formatter.

    GUARANTEES every detected intent appears as its own section by building each
    section programmatically from the fetched API data. The LLM is NOT trusted
    to enumerate categories — that was the source of the missing-section bug.

    Sections with no usable data show 'Data not available right now' rather than
    being silently dropped.

    The `user_email` and `model` args are kept for future LLM polishing, but the
    current implementation is purely deterministic for reliability.
    """
    intents: list[str] = list(multi_data.get("intents") or [])
    categories: dict[str, Any] = multi_data.get("categories") or {}

    if not intents:
        return "No live-data intents detected in the query."

    parts: list[str] = []
    for intent in intents:
        heading = _CATEGORY_HEADINGS.get(intent, intent.replace("_", " ").title())
        cat = categories.get(intent) or {}
        sources = cat.get("sources") or {}
        builder = _SECTION_BUILDERS.get(intent)
        body = builder(sources, query) if builder else "Data not available right now."
        parts.append(f"{heading}:\n{body}")

    parts.append("[Source: combined live APIs | Fetched: live]")
    # Suppress unused-arg warnings while keeping signature stable for future LLM polishing
    _ = (user_email, model)
    return "\n\n".join(parts)


def _detect_query_categories(query: str) -> list[str]:
    """Detect which data categories the query asks about. Used to enforce sectioned output."""
    q = query.lower()
    categories: list[str] = []
    if any(t in q for t in ["crypto", "bitcoin", "ethereum", "coin", "btc", "eth"]):
        categories.append("crypto")
    if any(t in q for t in ["weather", "temperature", "rain", "climate", "forecast"]):
        categories.append("weather")
    if any(t in q for t in ["stock", "share", "reliance", "nifty", "sensex", "tcs", "infy"]):
        categories.append("stocks")
    if any(t in q for t in ["mutual fund", "nav"]):
        categories.append("mutual_fund")
    if any(t in q for t in ["cricket", "ipl", "match", "score"]):
        categories.append("sports")
    if any(t in q for t in ["news", "headline", "headlines", "breaking", "latest news", "today news", "war", "conflict", "topic"]):
        categories.append("news")
    return categories


def ask_llm(query: str, data: dict[str, Any], user_email: str, model: str | None = None) -> str:
    """Ask the model to filter, format, and interpret live API results intelligently."""
    chosen = model or settings.LLM_MODEL
    client = get_llm_client()

    categories = _detect_query_categories(query)
    multi_category = len(categories) >= 2

    if multi_category:
        section_list = "\n".join(f"  - {_CATEGORY_HEADINGS[c]}" for c in categories if c in _CATEGORY_HEADINGS)
        system_prompt = (
            "You are an intelligent assistant. You receive structured real-time data from MULTIPLE APIs.\n"
            "Your job: combine ALL the data and answer the user query in a clean sectioned format.\n\n"
            "STRICT RULES:\n"
            "- Do NOT ignore any section of the data\n"
            "- Do NOT prioritize one source over another\n"
            "- You MUST include ALL detected categories below as separate sections\n"
            "- Do NOT hallucinate missing data — if a section has no data, say 'Data not available right now'\n"
            "- Use the EXACT section headings (with emojis) shown below\n\n"
            f"REQUIRED SECTIONS (in this order):\n{section_list}\n\n"
            "OUTPUT TEMPLATE:\n"
            "📊 Crypto Price:\n<one-line answer + 2-3 bullet details>\n\n"
            "🌦️ Weather in <location>:\n<temp + conditions>\n\n"
            "📰 Top Headlines:\n1. <title> — <source>\n2. ...\n3. ...\n\n"
            "End with: [Source: combined live APIs | Fetched: live]\n"
        )
        user_instructions = (
            "- Build ONE answer with all required sections above\n"
            "- Each section: extract the relevant fields from the matching API in the data below\n"
            "- For news section: list top 3-5 headlines with source attribution\n"
            "- For weather: include city/location if present in data\n"
            "- For prices: show currency and value clearly\n"
            "- Keep it readable, no JSON dumps"
        )
    else:
        system_prompt = (
            "You are a smart AI assistant with access to real-time data tools.\n\n"
            "DECISION LOGIC:\n"
            "1. Real-time API data is provided below. First check if it contains the answer.\n"
            "2. If the data IS relevant to the query — use it. Extract exactly what was asked.\n"
            "   - News/conflict/war: list headlines with dates and source names.\n"
            "   - Prices/numbers: show value with units and fetch time.\n"
            "   - Sports: show match names, scores, status.\n"
            "   - Weather: show temperature, conditions, location.\n"
            "3. If the data does NOT contain an answer to the query (e.g. calendar questions,\n"
            "   general knowledge, history, definitions) — answer from your training knowledge.\n"
            "   In that case do NOT mention live data and do NOT add a source tag.\n\n"
            "OUTPUT FORMAT (when using live data):\n"
            "- One-line direct answer first.\n"
            "- Key details in bullets or short paragraphs.\n"
            "- End with: [Source: {source name} | Fetched: live]\n\n"
            "OUTPUT FORMAT (when answering from training knowledge):\n"
            "- Just answer clearly and helpfully. No source tag needed.\n\n"
            "NEVER say 'I don't have real-time data' or 'as of my knowledge cutoff'.\n"
            "NEVER output 'No data found' — always give the best answer you can."
        )
        user_instructions = (
            "- If the data answers the query: extract the relevant parts, show top 5-10 results, "
            "use bullets or paragraphs, end with [Source: <name> | Fetched: live]\n"
            "- If the data does NOT answer the query: answer from your training knowledge normally.\n"
            "- Never say 'No data found'. Always give the best answer you can."
        )

    focused_data = _prepare_live_context(query, data)

    user_prompt = (
        f"User Query:\n{query}\n\n"
        f"Detected Categories: {categories or ['general']}\n\n"
        "Real-time API Data from MULTIPLE sources (use ALL relevant sections):\n"
        f"{_compact_json(focused_data, limit=12000)}\n\n"
        "Instructions:\n"
        f"{user_instructions}"
    )

    response = client.chat.completions.create(
        model=chosen,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=1500,
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
