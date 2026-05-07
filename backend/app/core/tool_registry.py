"""Tool registry — define available tools for function calling.

This module defines all tools that the LLM and router can invoke.
Tools are descriptive (for LLM awareness) but actual execution happens
in existing services (api_service, sql_service, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ToolCategory(str, Enum):
    """Tool categories."""

    DATA_FETCH = "data_fetch"  # External API calls
    DATABASE = "database"  # Local DB queries
    FILE = "file"  # File/spreadsheet operations
    IMAGE = "image"  # Image processing
    GENERATION = "generation"  # Content generation


@dataclass
class ToolParameter:
    """Tool parameter specification."""

    name: str
    type: str  # "string", "number", "boolean", "array"
    description: str
    required: bool = True
    enum_values: list[str] | None = None


@dataclass
class Tool:
    """Tool definition."""

    id: str
    name: str
    description: str
    category: ToolCategory
    parameters: list[ToolParameter]
    icon: str | None = None  # For UI representation

    def to_dict(self) -> dict:
        """Convert to dict for LLM consumption."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "enum": p.enum_values,
                }
                for p in self.parameters
            ],
        }


# Define all available tools
AVAILABLE_TOOLS = {
    # ── Data Fetch Tools ──────────────────────────────────────────
    "get_weather": Tool(
        id="get_weather",
        name="Get Weather",
        description="Fetch current weather and forecast for a location using Open-Meteo API",
        category=ToolCategory.DATA_FETCH,
        icon="🌤️",
        parameters=[
            ToolParameter(
                name="location",
                type="string",
                description="City or location name (e.g., 'New York', 'Mumbai')",
                required=True,
            ),
            ToolParameter(
                name="include_forecast",
                type="boolean",
                description="Include 7-day forecast",
                required=False,
            ),
        ],
    ),
    "get_news": Tool(
        id="get_news",
        name="Get News",
        description="Search and fetch news articles from multiple sources (The Hindu, Economic Times, NewsAPI, etc.)",
        category=ToolCategory.DATA_FETCH,
        icon="📰",
        parameters=[
            ToolParameter(
                name="query",
                type="string",
                description="Search query or topic",
                required=True,
            ),
            ToolParameter(
                name="source",
                type="string",
                description="Specific news source (optional)",
                required=False,
                enum_values=["the_hindu", "economic_times", "moneycontrol", "newsapi"],
            ),
        ],
    ),
    "get_crypto_price": Tool(
        id="get_crypto_price",
        name="Get Crypto Price",
        description="Fetch current cryptocurrency prices and market data",
        category=ToolCategory.DATA_FETCH,
        icon="₿",
        parameters=[
            ToolParameter(
                name="symbol",
                type="string",
                description="Crypto symbol (e.g., 'bitcoin', 'ethereum')",
                required=True,
            ),
            ToolParameter(
                name="currency",
                type="string",
                description="Price currency (default: USD)",
                required=False,
                enum_values=["usd", "inr", "eur"],
            ),
        ],
    ),
    "get_stock_price": Tool(
        id="get_stock_price",
        name="Get Stock Price",
        description="Fetch current stock prices and trends",
        category=ToolCategory.DATA_FETCH,
        icon="📈",
        parameters=[
            ToolParameter(
                name="symbol",
                type="string",
                description="Stock symbol (e.g., 'RELIANCE', 'TCS')",
                required=True,
            ),
        ],
    ),
    # ── Database Tools ──────────────────────────────────────────────
    "query_database": Tool(
        id="query_database",
        name="Query Database",
        description="Execute natural language queries against the database",
        category=ToolCategory.DATABASE,
        icon="🗄️",
        parameters=[
            ToolParameter(
                name="query",
                type="string",
                description="Natural language query",
                required=True,
            ),
            ToolParameter(
                name="limit",
                type="number",
                description="Max rows to return (default: 100)",
                required=False,
            ),
        ],
    ),
    # ── File Tools ──────────────────────────────────────────────────
    "analyze_spreadsheet": Tool(
        id="analyze_spreadsheet",
        name="Analyze Spreadsheet",
        description="Query and analyze data from uploaded Excel/CSV files",
        category=ToolCategory.FILE,
        icon="📊",
        parameters=[
            ToolParameter(
                name="file_name",
                type="string",
                description="Name of uploaded file",
                required=True,
            ),
            ToolParameter(
                name="query",
                type="string",
                description="Question about the data",
                required=True,
            ),
        ],
    ),
    "parse_file": Tool(
        id="parse_file",
        name="Parse File",
        description="Extract text content from uploaded files (PDF, DOCX, TXT, etc.)",
        category=ToolCategory.FILE,
        icon="📄",
        parameters=[
            ToolParameter(
                name="file_name",
                type="string",
                description="Name of uploaded file",
                required=True,
            ),
        ],
    ),
    # ── Image Tools ──────────────────────────────────────────────────
    "analyze_image": Tool(
        id="analyze_image",
        name="Analyze Image",
        description="Analyze, describe, and extract text from images",
        category=ToolCategory.IMAGE,
        icon="🖼️",
        parameters=[
            ToolParameter(
                name="image_url",
                type="string",
                description="URL or path to image",
                required=True,
            ),
            ToolParameter(
                name="analysis_type",
                type="string",
                description="Type of analysis",
                required=False,
                enum_values=["describe", "extract_text", "ocr", "classification"],
            ),
        ],
    ),
    # ── Generation Tools ──────────────────────────────────────────────
    "generate_image": Tool(
        id="generate_image",
        name="Generate Image",
        description="Generate images using AI image generation",
        category=ToolCategory.GENERATION,
        icon="🎨",
        parameters=[
            ToolParameter(
                name="prompt",
                type="string",
                description="Detailed image description",
                required=True,
            ),
        ],
    ),
}


class ToolRegistry:
    """Registry for managing tools and their availability."""

    _tools = AVAILABLE_TOOLS

    @classmethod
    def get_tool(cls, tool_id: str) -> Tool | None:
        """Get tool by ID."""
        return cls._tools.get(tool_id)

    @classmethod
    def get_tools_by_category(cls, category: ToolCategory) -> list[Tool]:
        """Get all tools in a category."""
        return [t for t in cls._tools.values() if t.category == category]

    @classmethod
    def list_tools(cls) -> list[Tool]:
        """List all available tools."""
        return list(cls._tools.values())

    @classmethod
    def get_tools_for_intent(cls, intent: str) -> list[Tool]:
        """Get tools relevant to a detected intent."""
        intent_lower = intent.lower()

        # Map intents to tool categories/IDs
        intent_tools = {
            "weather": ["get_weather"],
            "news": ["get_news"],
            "crypto": ["get_crypto_price"],
            "stocks": ["get_stock_price"],
            "database": ["query_database"],
            "file": ["analyze_spreadsheet", "parse_file"],
            "image": ["analyze_image"],
            "general": [],
        }

        tool_ids = intent_tools.get(intent_lower, [])
        return [cls._tools[tid] for tid in tool_ids if tid in cls._tools]

    @classmethod
    def register_tool(cls, tool: Tool) -> None:
        """Register a custom tool."""
        cls._tools[tool.id] = tool

    @classmethod
    def to_openai_format(cls) -> list[dict]:
        """Convert tools to OpenAI function calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.id,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            p.name: {
                                "type": p.type,
                                "description": p.description,
                                "enum": p.enum_values,
                            }
                            for p in tool.parameters
                        },
                        "required": [p.name for p in tool.parameters if p.required],
                    },
                },
            }
            for tool in cls._tools.values()
        ]
