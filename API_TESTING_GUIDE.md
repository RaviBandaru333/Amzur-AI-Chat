# Live Data API Integration Testing Guide

This document provides comprehensive examples to test all integrated APIs in the AI Chat live-data system.

## Prerequisites

```bash
# Install required tools
curl --version  # Should be installed by default on Windows PowerShell
# Or use: Invoke-WebRequest in PowerShell

# Set environment variables in .env
NEWSAPI_KEY=your_newsapi_org_key
CRICAPI_KEY=your_cricapi_key
THENEWSAPI_TOKEN=your_thenewsapi_token
```

## Backend Configuration

Add these to `backend/.env`:

```env
# Live Data API Settings
LIVE_API_TIMEOUT_SECONDS=12

# News APIs
NEWSAPI_KEY=                    # Get from: https://newsapi.org/
CRICAPI_KEY=                    # Get from: https://www.cricapi.com/
THENEWSAPI_TOKEN=               # Get from: https://www.thenewsapi.com/

# Backend server
BACKEND_PUBLIC_URL=http://localhost:8000
```

---

## API Categories & Examples

### 1. **Sports & Cricket**

#### Cricket Events (TheSportsDB)
```bash
# Direct API call
curl "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d=2026-05-05&s=Cricket"

# Via Chatbot - Ask for cricket matches
POST /api/live
{
  "query": "What cricket matches are happening today?"
}
```

#### Current Cricket Matches (CricAPI)
```bash
# Requires CRICAPI_KEY in .env
curl "https://api.cricapi.com/v1/currentMatches?apikey=YOUR_KEY&offset=0"

# Via Chatbot
{
  "query": "Show current cricket matches"
}
```

---

### 2. **Weather & Location**

#### Current Weather (Open-Meteo - No Key Required)
```bash
# Chennai weather
curl "https://api.open-meteo.com/v1/forecast?latitude=13.08&longitude=80.27&current_weather=true"

# Via Chatbot
{
  "query": "What's the weather in Chennai today?"
}
```

#### IP Geolocation (ip-api.com - No Key Required)
```bash
# Your public IP and location
curl "http://ip-api.com/json/"

# Via Chatbot
{
  "query": "What's my current location?"
}
```

---

### 3. **Cryptocurrency**

#### Bitcoin Price (CoinGecko - No Key Required)
```bash
# Bitcoin current price
curl "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"

# Via Chatbot
{
  "query": "What's the current Bitcoin price?"
}
```

---

### 4. **Finance & Markets**

#### Reliance Stock (Yahoo Finance - No Key Required)
```bash
# 1 month historical data
curl "https://query1.finance.yahoo.com/v8/finance/chart/RELIANCE.NS?interval=1d&range=1mo"

# Via Chatbot
{
  "query": "Show Reliance stock price trends for last month"
}
```

#### Mutual Fund Master (MF API - No Key Required)
```bash
# All Indian mutual funds
curl "https://api.mfapi.in/mf"

# Via Chatbot
{
  "query": "List available mutual funds in India"
}
```

---

### 5. **News Sources**

#### Inshorts Technology News (No Key Required)
```bash
# Technology news
curl "https://inshorts.deta.dev/news?category=technology"

# Via Chatbot
{
  "query": "Show latest technology news"
}
```

#### NewsAPI Business Headlines (Requires Key)
```bash
# India business headlines
curl "https://newsapi.org/v2/top-headlines?country=in&category=business&apiKey=YOUR_NEWSAPI_KEY"

# Via Chatbot
{
  "query": "Get latest business news from India"
}
```

#### TheNewsAPI - Multiple News Sources
```bash
# Top headlines (India)
curl "https://api.thenewsapi.com/v1/news/top?api_token=YOUR_TOKEN&locale=in&language=en"

# Business news (India)
curl "https://api.thenewsapi.com/v1/news/top?api_token=YOUR_TOKEN&locale=in&categories=business&language=en"

# Tech & Finance
curl "https://api.thenewsapi.com/v1/news/top?api_token=YOUR_TOKEN&categories=tech,business&locale=in&language=en"

# Search - Mutual Funds
curl "https://api.thenewsapi.com/v1/news/all?api_token=YOUR_TOKEN&search=mutual+fund+india&language=en&limit=5"

# Via Chatbot
{
  "query": "Show tech and business news headlines"
}
```

---

### 6. **RSS News Feeds (RSS2JSON - No Key Required)**

#### The Hindu News
```bash
# Direct via RSS2JSON
curl "https://api.rss2json.com/v1/api.json?rss_url=https://www.thehindu.com/feeder/default.rss"

# Via Chatbot
{
  "query": "Get latest news from The Hindu"
}
```

#### Economic Times Markets
```bash
curl "https://api.rss2json.com/v1/api.json?rss_url=https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"

# Via Chatbot
{
  "query": "Show market news from Economic Times"
}
```

#### Moneycontrol Finance News
```bash
curl "https://api.rss2json.com/v1/api.json?rss_url=https://www.moneycontrol.com/rss/latestnews.xml"

# Via Chatbot
{
  "query": "Get latest finance news from Moneycontrol"
}
```

#### NDTV India News
```bash
curl "https://api.rss2json.com/v1/api.json?rss_url=https://feeds.feedburner.com/ndtvnews-india-newscl"

# Via Chatbot
{
  "query": "Show India news from NDTV"
}
```

---

### 7. **Country Information**

#### India Country Data (No Key Required)
```bash
# India information
curl "https://restcountries.com/v3.1/name/india"

# Via Chatbot
{
  "query": "Tell me about India"
}
```

---

## Testing the Live Data Endpoint

### Test Endpoint Structure

```bash
# Backend endpoint for live data
POST http://localhost:8000/api/live/query
Content-Type: application/json
Authorization: Bearer <JWT_TOKEN>

{
  "query": "What's happening in cricket today?"
}
```

### PowerShell Examples

```powershell
# Set token
$token = "YOUR_JWT_TOKEN"

# Sports Query
$body = @{
    query = "Show current cricket matches"
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:8000/api/live/query" `
    -Method POST `
    -Headers @{
        "Authorization" = "Bearer $token"
        "Content-Type" = "application/json"
    } `
    -Body $body

# News Query
$body = @{
    query = "Get latest technology news"
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:8000/api/live/query" `
    -Method POST `
    -Headers @{
        "Authorization" = "Bearer $token"
        "Content-Type" = "application/json"
    } `
    -Body $body

# Finance Query
$body = @{
    query = "Show Bitcoin price and Reliance stock trends"
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:8000/api/live/query" `
    -Method POST `
    -Headers @{
        "Authorization" = "Bearer $token"
        "Content-Type" = "application/json"
    } `
    -Body $body
```

---

## LLM Filtering & Formatting

### How It Works

1. **User Query**: "Show me the top 5 cricket matches happening today"
2. **API Fetch**: Backend fetches from TheSportsDB and CricAPI
3. **LLM Filtering**: Model filters results to show ONLY top 5, formats as table
4. **Output**: Clean, readable list with:
   - Match name
   - Teams
   - Time/Status
   - Source attribution

### Filtering Examples

```
Query: "How many cricket matches today?"
LLM Output: "3 cricket matches scheduled for today:
1. [Team A] vs [Team B] - 2:00 PM IST
2. [Team C] vs [Team D] - 5:00 PM IST
3. [Team E] vs [Team F] - 8:00 PM IST"

Query: "Show top business news"
LLM Output: "Top 5 business headlines:
• Title 1 - Source: NewsAPI
• Title 2 - Source: The Hindu RSS
• Title 3 - Source: Economic Times RSS
• Title 4 - Source: TheNewsAPI
• Title 5 - Source: Moneycontrol RSS"

Query: "Bitcoin and crypto prices"
LLM Output: "Cryptocurrency Prices:
• Bitcoin (BTC): $XXXXX USD
• Ethereum (ETH): $XXXXX USD
Source: CoinGecko (Updated: 2:15 PM IST)"
```

---

## Integration Testing Checklist

- [ ] **Sports APIs**
  - [ ] Cricket matches display correctly
  - [ ] CricAPI working with key
  - [ ] Data filtered to match query

- [ ] **Weather APIs**
  - [ ] Current weather fetches
  - [ ] Location detection works
  - [ ] Multiple locations supported

- [ ] **Crypto APIs**
  - [ ] Bitcoin price fetches
  - [ ] Price displays with currency
  - [ ] Real-time updates work

- [ ] **Finance APIs**
  - [ ] Stock data retrieves correctly
  - [ ] Mutual fund list loads
  - [ ] Chart data displays without clipping

- [ ] **News APIs**
  - [ ] NewsAPI working with key
  - [ ] TheNewsAPI filtering works
  - [ ] Inshorts news loads
  - [ ] Multiple sources return data

- [ ] **RSS Feeds**
  - [ ] The Hindu RSS parses
  - [ ] Economic Times RSS works
  - [ ] Moneycontrol RSS fetches
  - [ ] NDTV RSS loads

- [ ] **LLM Filtering**
  - [ ] Model filters to user query
  - [ ] Output is readable
  - [ ] Source attribution present
  - [ ] No fabricated data

- [ ] **Chart UI**
  - [ ] Charts render without clipping
  - [ ] Labels fully visible
  - [ ] Horizontal scroll works
  - [ ] Charts are large enough

---

## Troubleshooting

### No Data Returned

```
Problem: API returns empty or error
Solution:
1. Check API key in .env (if required)
2. Verify internet connection
3. Check API status/uptime
4. Increase LIVE_API_TIMEOUT_SECONDS in .env
```

### Clipped Labels

```
Problem: Chart labels are cut off
Solution:
1. Increase margin in ChartCard.tsx
2. Reduce data points per chart
3. Use horizontal scroll (already enabled)
```

### LLM Not Filtering

```
Problem: LLM returns all data instead of filtered
Solution:
1. Update system prompt in llm_service.py
2. Check LLM model is chat-capable
3. Verify API data is structured JSON
```

---

## API Response Examples

### Cricket Match Response
```json
{
  "source": "sports_cricket_events",
  "ok": true,
  "status_code": 200,
  "data": {
    "results": [
      {
        "idEvent": "12345",
        "strEvent": "Team A vs Team B",
        "strEventTime": "14:00",
        "strDate": "2026-05-05"
      }
    ]
  }
}
```

### Weather Response
```json
{
  "source": "weather_open_meteo",
  "ok": true,
  "status_code": 200,
  "data": {
    "current_weather": {
      "temperature": 28.5,
      "windspeed": 12.3,
      "weathercode": 0
    }
  }
}
```

### News Response (RSS2JSON)
```json
{
  "source": "rss_the_hindu_news",
  "ok": true,
  "status_code": 200,
  "data": {
    "items": [
      {
        "title": "News Headline",
        "description": "Short description",
        "link": "https://...",
        "pubDate": "2026-05-05"
      }
    ]
  }
}
```

---

## Environment Variables Reference

```env
# API Timeouts
LIVE_API_TIMEOUT_SECONDS=12

# Required API Keys
NEWSAPI_KEY=sk_live_...                    # From: https://newsapi.org/
CRICAPI_KEY=...                            # From: https://www.cricapi.com/
THENEWSAPI_TOKEN=...                       # From: https://www.thenewsapi.com/

# Optional
BACKEND_PUBLIC_URL=http://localhost:8000
```

## Free APIs Used (No Key Required)
- ✅ TheSportsDB (Cricket events)
- ✅ Open-Meteo (Weather)
- ✅ CoinGecko (Crypto prices)
- ✅ ip-api.com (Geolocation)
- ✅ Yahoo Finance (Stock data)
- ✅ MF API (Mutual funds)
- ✅ Inshorts (Technology news)
- ✅ RSS2JSON (News feeds)
- ✅ REST Countries (Country data)

## Free APIs Requiring Keys
- 🔑 NewsAPI.org (Business headlines)
- 🔑 CricAPI (Current matches)
- 🔑 TheNewsAPI (Multiple news categories)

---

## Support

For issues or questions:
1. Check logs in `backend/logs/` directory
2. Verify .env variables are set correctly
3. Test APIs directly with curl first
4. Check API provider status pages
5. Review LLM response format in llm_service.py
