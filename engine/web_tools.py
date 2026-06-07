"""
web_tools.py
Kalshi Agent v3.0 — Live Internet Search
Uses DuckDuckGo Search to pull breaking news about any ticker or event.
Injects results directly into the LLM prompt as a ## LIVE SEARCH block.

USAGE in any strategy's build_context():
    from engine.web_tools import search_breaking_news
    news_block = search_breaking_news("CPI inflation May 2026")
    if news_block:
        prompt_sections.append(news_block)

REQUIRES: pip install duckduckgo-search
"""

try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, l, e, t, m): print(f"[{l}] {e} | {t} | {m}")
    logger = _FallbackLogger()


def search_breaking_news(query: str, max_results: int = 3) -> str:
    """
    Searches the live internet for recent news about a specific ticker or event.

    Returns a formatted ## LIVE INTERNET SEARCH RESULTS block ready to
    append to prompt_sections, or an empty string if search is unavailable.

    query:       What to search — e.g. "CPI inflation report May 2026"
    max_results: How many articles to include (default 3, keep low for token budget)
    """
    if not DDGS_AVAILABLE:
        logger.log_event(
            "WARNING", "WEB_SEARCH_SKIP", "SYSTEM",
            "duckduckgo-search not installed. Run: pip install duckduckgo-search"
        )
        return ""

    try:
        results = DDGS().text(
            query + " breaking news today",
            max_results = max_results,
            safesearch  = 'off'
        )

        if not results:
            return ""

        news_block = "## LIVE INTERNET SEARCH RESULTS\n"
        for i, r in enumerate(results, 1):
            title   = r.get('title', 'No title')
            body    = r.get('body', 'No content')[:300]  # Cap body length
            news_block += f"{i}. {title}\n   Context: {body}\n\n"

        logger.log_event(
            "INFO", "WEB_SEARCH_OK", "SYSTEM",
            f"Scraped {len(results)} articles for '{query}'"
        )
        return news_block

    except Exception as e:
        logger.log_event("ERROR", "WEB_SEARCH_FAIL", "SYSTEM", str(e))
        return ""


if __name__ == "__main__":
    print("Testing Web Search Engine...\n")
    result = search_breaking_news("S&P 500 Market", 2)
    print(result if result else "No results or ddgs not installed.")
