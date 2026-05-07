"""Zero-shot ReAct agent over live-data tools.

Why this file exists
--------------------
The chat backend already has reliable, deterministic live-data fetchers in
`app.services.api_service` (weather, crypto, news, etc.). This module gives the
LLM autonomy to *decide* which of those fetchers to call — and call several of
them when the user asks a multi-part question — without any if/else routing.

Design rules followed
---------------------
* Tool count is **deliberately focused** (6 tools — weather, crypto, news,
  sports, stocks, mutual_fund) so the agent has one tool per live-data
  intent the chat backend already supports. More tools => worse selection
  accuracy, so we stop here.
* Tool descriptions are **action-oriented and explicit** about when to use the
  tool, what the input shape is, and what the output looks like. The agent
  picks tools based on these descriptions, so they are the most important
  prompt surface.
* The agent uses LangChain's classic `initialize_agent` with
  `AgentType.ZERO_SHOT_REACT_DESCRIPTION`, exactly as required by the spec.
* All LLM calls go through the LiteLLM proxy (`get_chat_llm()`).
* Intermediate steps (Thought / Action / Observation) are surfaced both in the
  HTTP response body and as Server-Sent-Events for the UI's "AI is thinking…"
  panel.
"""
from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any, AsyncIterator, Callable, Iterator

from langchain.agents import AgentExecutor, AgentType, initialize_agent
from langchain.callbacks.base import BaseCallbackHandler
from langchain_core.tools import tool

from app.ai.llm import get_chat_llm
from app.services import api_service


# ──────────────────────────────────────────────────────────────────────────────
# Tools — keep the set small and the descriptions sharp.
# ──────────────────────────────────────────────────────────────────────────────


@tool("get_weather", return_direct=False)
def get_weather(city: str) -> str:
    """Get the current weather AND short-term forecast for a single named city.

    Use this whenever the user asks about temperature, weather, rain, humidity,
    climate, or forecast (today, tomorrow, or the next couple of days) for a
    specific place. The tool returns current conditions plus a 3-day daily
    forecast including the maximum probability of rain per day, so it CAN
    answer questions like "chance of rain tomorrow in <city>".

    Args:
        city: A city name (e.g. "Visakhapatnam", "Mumbai", "London"). Pass only
            the city name — do not include the word "weather" or any punctuation.

    Returns:
        A short human-readable string with current temperature/wind/humidity
        plus a per-day forecast (today, tomorrow, day-after) with min/max
        temperature and the maximum chance of rain for each day. Source is
        Open-Meteo. Returns an error string if the city cannot be resolved.
    """
    if not city or not city.strip():
        return "ERROR: city name is required."
    result = api_service._weather_for_query(f"weather in {city.strip()}")
    if not result.get("ok"):
        return f"ERROR: weather lookup failed ({result.get('error')}: {result.get('message')})."

    data = result.get("data") or {}
    cw = data.get("current_weather") or {}
    location = data.get("location_name") or city
    parts: list[str] = [f"Current weather in {location}"]
    if cw.get("temperature") is not None:
        parts.append(f"temperature {cw['temperature']}°C")
    if cw.get("windspeed") is not None:
        parts.append(f"wind {cw['windspeed']} km/h")

    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    cw_time = cw.get("time")
    if cw_time and cw_time in times:
        idx = times.index(cw_time)
        humidity_arr = hourly.get("relative_humidity_2m") or []
        precip_arr = hourly.get("precipitation_probability") or []
        if idx < len(humidity_arr) and humidity_arr[idx] is not None:
            parts.append(f"humidity {humidity_arr[idx]}%")
        if idx < len(precip_arr) and precip_arr[idx] is not None:
            parts.append(f"current rain chance {precip_arr[idx]}%")

    current_line = ", ".join(parts) + "."

    # Per-day forecast: today / tomorrow / day after, with max rain probability.
    daily = data.get("daily") or {}
    d_times = daily.get("time") or []
    tmaxs = daily.get("temperature_2m_max") or []
    tmins = daily.get("temperature_2m_min") or []
    pmax = daily.get("precipitation_probability_max") or []
    psum = daily.get("precipitation_sum") or []
    labels = ["Today", "Tomorrow", "Day after"]
    forecast_lines: list[str] = []
    for i, label in enumerate(labels):
        if i >= len(d_times):
            break
        bits: list[str] = []
        if i < len(tmins) and i < len(tmaxs) and tmins[i] is not None and tmaxs[i] is not None:
            bits.append(f"{tmins[i]}°C – {tmaxs[i]}°C")
        if i < len(pmax) and pmax[i] is not None:
            bits.append(f"chance of rain {pmax[i]}%")
        if i < len(psum) and psum[i] is not None:
            bits.append(f"precipitation {psum[i]} mm")
        if bits:
            forecast_lines.append(f"  - {label} ({d_times[i]}): " + ", ".join(bits))

    if forecast_lines:
        current_line += "\nForecast:\n" + "\n".join(forecast_lines)

    return current_line + "\n(source: Open-Meteo)"


@tool("get_crypto", return_direct=False)
def get_crypto(symbol: str) -> str:
    """Get the current USD price for a cryptocurrency.

    Use this for any question about a coin's price, value, or how much it
    costs right now (Bitcoin, Ethereum, etc.).

    Args:
        symbol: Coin name or ticker, e.g. "bitcoin", "btc", "ethereum", "eth".

    Returns:
        A human-readable string with the current USD price, or an error message
        if the price cannot be fetched.

    Note:
        The underlying CoinGecko endpoint currently exposes Bitcoin only; other
        symbols will fall back to Bitcoin until the source is expanded.
    """
    sym = (symbol or "").strip().lower()
    if not sym:
        return "ERROR: symbol is required."
    result = api_service._bitcoin_price()
    if not result.get("ok"):
        return f"ERROR: crypto lookup failed ({result.get('error')}: {result.get('message')})."
    data = result.get("data") or {}
    btc = data.get("bitcoin") or {}
    price = btc.get("usd")
    if price is None:
        return "ERROR: price not present in CoinGecko response."
    label = "Bitcoin" if sym in {"bitcoin", "btc"} else f"Bitcoin (closest available match for '{symbol}')"
    return f"{label} is currently ${price:,} USD (source: CoinGecko)."


@tool("get_news", return_direct=False)
def get_news(topic: str = "") -> str:
    """Get the latest news headlines, optionally filtered by topic.

    Use this whenever the user asks for news, headlines, top stories, breaking
    news, or news about a specific subject (e.g. "iran usa war", "ai regulation").

    Args:
        topic: Optional free-text topic. Pass an empty string to get general
            top headlines for India.

    Returns:
        A newline-separated list of up to 5 headline-source pairs, or an error
        message if no news source could be reached.
    """
    topic_clean = (topic or "").strip()
    sources: dict[str, dict] = {}

    if topic_clean:
        sources["thenewsapi_topic_search"] = api_service._thenews_topic_search(topic_clean)

    sources["rss_the_hindu_news"] = api_service._rss_the_hindu()
    sources["rss_ndtv_india_news"] = api_service._rss_ndtv()
    sources["thenewsapi_top_india"] = api_service._thenews_top_india()

    seen: set[str] = set()
    bullets: list[str] = []

    def add(items: list, label: str) -> None:
        for item in items:
            if len(bullets) >= 5:
                return
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            if not title or title.lower() in seen:
                continue
            seen.add(title.lower())
            bullets.append(f"{len(bullets) + 1}. {title} — {label}")

    if topic_clean:
        topic_data = (sources.get("thenewsapi_topic_search") or {}).get("data") or {}
        add(topic_data.get("data") or [], f"TheNewsAPI ({topic_clean})")
    add(((sources.get("rss_the_hindu_news") or {}).get("data") or {}).get("items") or [], "The Hindu")
    add(((sources.get("rss_ndtv_india_news") or {}).get("data") or {}).get("items") or [], "NDTV")
    add(((sources.get("thenewsapi_top_india") or {}).get("data") or {}).get("data") or [], "TheNewsAPI India")

    if not bullets:
        return "ERROR: no news source returned data right now."
    header = f"Top headlines{(' for ' + topic_clean) if topic_clean else ''}:"
    return header + "\n" + "\n".join(bullets)


@tool("get_sports", return_direct=False)
def get_sports(query: str = "") -> str:
    """Get today's cricket matches and currently-live cricket scores.

    Use this whenever the user asks about cricket, IPL, matches, scores,
    fixtures, or "what's happening in sports today". Covers BOTH today's
    scheduled events AND any matches that are currently live.

    Args:
        query: Optional free-text hint (e.g. "ipl today", "live cricket score").
            Currently used only for logging — the underlying APIs return all
            cricket events for today.

    Returns:
        A multi-line string listing today's matches and any currently-live
        cricket scores, with source attribution. Returns an error string if
        no sports data source could be reached.
    """
    _ = query  # accepted for ReAct symmetry
    lines: list[str] = []

    ev = api_service._sports_events_today()
    if ev.get("ok"):
        events = ((ev.get("data") or {}).get("events")) or []
        bullets: list[str] = []
        for item in events[:5]:
            if not isinstance(item, dict):
                continue
            title = item.get("strEvent") or "Match"
            date = item.get("dateEvent") or ""
            t = item.get("strTime") or ""
            status = item.get("strStatus") or ""
            bullet = f"- {title} {date} {t} {status}".strip()
            if bullet:
                bullets.append(bullet)
        if bullets:
            lines.append("Today's cricket matches (TheSportsDB):")
            lines.extend(bullets)

    cm = api_service._cricapi_current_matches()
    if cm.get("ok"):
        items = ((cm.get("data") or {}).get("data")) or []
        bullets = []
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or "Match"
            status = item.get("status") or ""
            bullet = f"- {name} — {status}".strip(" —")
            if bullet:
                bullets.append(bullet)
        if bullets:
            if lines:
                lines.append("")
            lines.append("Currently-live matches (CricAPI):")
            lines.extend(bullets)

    if not lines:
        return "ERROR: no sports data source returned data right now."
    return "\n".join(lines)


@tool("get_stocks", return_direct=False)
def get_stocks(query: str = "") -> str:
    """Get the latest equity-market snapshot for India.

    Use this whenever the user asks about stocks, share price, Reliance, Nifty,
    Sensex, the stock market, or general market headlines. The tool returns
    the live Reliance (RELIANCE.NS) price plus a few headline market news
    bullets from Economic Times / Moneycontrol.

    Args:
        query: Optional free-text hint (e.g. "reliance share price", "nifty
            today"). Currently informational — the underlying APIs return a
            fixed snapshot.

    Returns:
        A multi-line string with the Reliance price and recent market headlines,
        each with source attribution. Returns an error string if no source
        could be reached.
    """
    _ = query  # accepted for ReAct symmetry
    lines: list[str] = []

    yh = api_service._yahoo_reliance()
    if yh.get("ok"):
        chart = (yh.get("data") or {}).get("chart") or {}
        result = chart.get("result") or []
        if result and isinstance(result[0], dict):
            meta = result[0].get("meta") or {}
            symbol = meta.get("symbol", "RELIANCE.NS")
            currency = meta.get("currency", "INR")
            price = meta.get("regularMarketPrice")
            if price is not None:
                lines.append(f"{symbol}: {price} {currency} (source: Yahoo Finance)")

    for key, fetch, label in (
        ("rss_economic_times_markets", api_service._rss_economic_times, "Economic Times"),
        ("rss_moneycontrol_finance", api_service._rss_moneycontrol, "Moneycontrol"),
    ):
        feed = fetch()
        if not feed.get("ok"):
            continue
        items = ((feed.get("data") or {}).get("items")) or []
        titles = [i.get("title") for i in items[:3] if isinstance(i, dict) and i.get("title")]
        if titles:
            if lines:
                lines.append("")
            lines.append(f"Latest market headlines ({label}):")
            lines.extend(f"- {t}" for t in titles)
            break  # one feed of headlines is enough

    if not lines:
        return "ERROR: no stock-market data source returned data right now."
    return "\n".join(lines)


@tool("get_mutual_fund", return_direct=False)
def get_mutual_fund(query: str = "") -> str:
    """Get mutual-fund information and recent mutual-fund news.

    Use this whenever the user asks about mutual funds, MF NAV, MF schemes,
    or mutual-fund news. Returns the count of indexed schemes from mfapi.in
    plus up to 3 recent mutual-fund headlines.

    Args:
        query: Optional free-text hint (e.g. "best mutual fund 2026"). Currently
            informational.

    Returns:
        A multi-line string with the scheme count and recent MF headlines, each
        with source attribution. Returns an error string if no source could
        be reached.
    """
    _ = query
    lines: list[str] = []

    mf = api_service._mutual_fund_master()
    if mf.get("ok"):
        data = mf.get("data") or []
        if isinstance(data, list) and data:
            lines.append(f"Mutual fund master list: {len(data):,} schemes indexed (source: mfapi.in)")

    nf = api_service._thenews_search_mutual_fund()
    if nf.get("ok"):
        items = ((nf.get("data") or {}).get("data")) or []
        titles = [i.get("title") for i in items[:3] if isinstance(i, dict) and i.get("title")]
        if titles:
            if lines:
                lines.append("")
            lines.append("Recent mutual-fund news (TheNewsAPI):")
            lines.extend(f"- {t}" for t in titles)

    if not lines:
        return "ERROR: no mutual-fund data source returned data right now."
    return "\n".join(lines)


# Module-level tool list so the executor (and any future tests) share one
# source of truth. Kept intentionally focused — one tool per intent category
# the inline chat already supports.
TOOLS = [get_weather, get_crypto, get_news, get_sports, get_stocks, get_mutual_fund]


# ──────────────────────────────────────────────────────────────────────────────
# Streaming-friendly callback handler — translates LangChain agent events into
# small typed events that the FastAPI route can forward to the UI as SSE.
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class StreamingAgentEvent:
    """Single event emitted while the agent is running.

    `type` is one of:
        - "thinking": agent started, no observation yet
        - "tool_start": about to call a tool (with name + input)
        - "tool_end":  tool finished (with truncated output)
        - "final":     final answer ready
        - "error":     unrecoverable failure
    """

    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "data": self.data}


class _QueueCallbackHandler(BaseCallbackHandler):
    """Pushes lightweight progress events onto a thread-safe queue."""

    def __init__(self, queue: "Queue[StreamingAgentEvent | None]") -> None:
        super().__init__()
        self._queue = queue

    # ── chain ────────────────────────────────────────────────────────────────
    def on_chain_start(self, serialized: dict, inputs: dict, **_: Any) -> None:
        self._queue.put(StreamingAgentEvent(
            "thinking",
            {"message": "Agent is thinking…"},
        ))

    # ── tools ────────────────────────────────────────────────────────────────
    def on_tool_start(self, serialized: dict, input_str: str, **_: Any) -> None:
        name = (serialized or {}).get("name") or "tool"
        self._queue.put(StreamingAgentEvent(
            "tool_start",
            {"tool": name, "input": (input_str or "")[:300], "message": f"Calling {name}…"},
        ))

    def on_tool_end(self, output: str, **_: Any) -> None:
        text = output if isinstance(output, str) else str(output)
        self._queue.put(StreamingAgentEvent(
            "tool_end",
            {"output": text[:600], "truncated": len(text) > 600},
        ))

    def on_tool_error(self, error: BaseException, **_: Any) -> None:
        self._queue.put(StreamingAgentEvent(
            "tool_end",
            {"output": f"Tool error: {error}", "error": True},
        ))

    # ── agent ────────────────────────────────────────────────────────────────
    def on_agent_action(self, action: Any, **_: Any) -> None:
        # Surface the agent's reasoning text (the "Thought:" portion of ReAct)
        # so the UI can show it.
        log = getattr(action, "log", "") or ""
        thought = log.split("Action:")[0].strip()
        if thought:
            self._queue.put(StreamingAgentEvent(
                "thinking",
                {"message": thought[:400]},
            ))


# ──────────────────────────────────────────────────────────────────────────────
# Executor builder + runners.
# ──────────────────────────────────────────────────────────────────────────────


def build_agent_executor(
    *,
    user_email: str,
    callbacks: list[BaseCallbackHandler] | None = None,
    verbose: bool = True,
) -> AgentExecutor:
    """Construct a zero-shot ReAct agent bound to the LiteLLM-proxied LLM.

    A fresh executor is built per request because the agent embeds the
    callbacks and per-user metadata. The LLM client itself is cached.
    """
    base_llm = get_chat_llm()
    # Bind per-user tracking metadata so LiteLLM cost reports carry the email.
    llm = base_llm.bind(
        user=user_email,
        extra_body={"metadata": {"application": "amzur-ai-chat", "test_type": "agent"}},
    )

    return initialize_agent(
        tools=TOOLS,
        llm=llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=verbose,
        handle_parsing_errors=True,
        max_iterations=8,
        early_stopping_method="generate",
        return_intermediate_steps=True,
        callbacks=callbacks or [],
    )


def run_agent(query: str, *, user_email: str) -> dict[str, Any]:
    """Run the agent synchronously and return the final answer + steps.

    Used by callers that want one consolidated JSON response (no streaming).
    """
    executor = build_agent_executor(user_email=user_email)
    try:
        result = executor.invoke({"input": query})
    except Exception as exc:
        return {
            "ok": False,
            "answer": f"Agent failed: {exc}",
            "steps": [],
        }
    steps_serialised: list[dict[str, Any]] = []
    for action, observation in result.get("intermediate_steps") or []:
        steps_serialised.append({
            "tool": getattr(action, "tool", "unknown"),
            "tool_input": getattr(action, "tool_input", ""),
            "log": getattr(action, "log", ""),
            "observation": observation if isinstance(observation, str) else str(observation),
        })
    return {
        "ok": True,
        "answer": (result.get("output") or "").strip(),
        "steps": steps_serialised,
    }


async def stream_agent(query: str, *, user_email: str) -> AsyncIterator[StreamingAgentEvent]:
    """Run the agent in a background thread and yield live progress events.

    The agent itself is synchronous (LangChain `initialize_agent`), so we run
    it in a worker thread and bridge the callback queue into an async iterator.
    The route handler can forward the events as Server-Sent Events.
    """
    queue: "Queue[StreamingAgentEvent | None]" = Queue()
    callback = _QueueCallbackHandler(queue)

    final_holder: dict[str, Any] = {}

    def _worker() -> None:
        try:
            executor = build_agent_executor(user_email=user_email, callbacks=[callback])
            result = executor.invoke({"input": query})
            final_holder["answer"] = (result.get("output") or "").strip()
            final_holder["steps"] = []
            for action, observation in result.get("intermediate_steps") or []:
                final_holder["steps"].append({
                    "tool": getattr(action, "tool", "unknown"),
                    "tool_input": getattr(action, "tool_input", ""),
                    "log": getattr(action, "log", ""),
                    "observation": observation if isinstance(observation, str) else str(observation),
                })
        except Exception as exc:  # noqa: BLE001 — we want every failure surfaced
            final_holder["error"] = str(exc)
        finally:
            queue.put(None)  # sentinel: agent finished

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    loop = asyncio.get_running_loop()

    while True:
        # Bridge the blocking queue.get into the running event loop.
        event = await loop.run_in_executor(None, _safe_get, queue)
        if event is None:
            break
        yield event

    if "error" in final_holder:
        yield StreamingAgentEvent("error", {"message": final_holder["error"]})
    else:
        yield StreamingAgentEvent(
            "final",
            {
                "answer": final_holder.get("answer", ""),
                "steps": final_holder.get("steps", []),
            },
        )


def _safe_get(queue: "Queue[StreamingAgentEvent | None]") -> StreamingAgentEvent | None:
    """Block on queue.get with a sane periodic wake-up (cancels stay responsive)."""
    while True:
        try:
            return queue.get(timeout=0.5)
        except Empty:
            continue


def event_to_sse(event: StreamingAgentEvent) -> bytes:
    """Encode a StreamingAgentEvent as an SSE `data:` line."""
    payload = json.dumps(event.to_dict(), ensure_ascii=False)
    return f"data: {payload}\n\n".encode("utf-8")
