from ddgs import DDGS

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, l, e, t, m): print(f"[{l}] {e} | {t} | {m}")
    logger = _FallbackLogger()

def search_breaking_news(query: str, max_results: int = 3) -> str:
    """Searches the live internet for recent news regarding a specific ticker/event."""
    try:
        results = DDGS().text(query + " breaking news today", max_results=max_results, safesearch='off')
        if not results:
            return "No recent breaking news found."
        
        news_block = "## LIVE INTERNET SEARCH RESULTS:\n"
        for i, r in enumerate(results, 1):
            news_block += f"{i}. {r.get('title')}\n   Context: {r.get('body')}\n"
        
        logger.log_event("INFO", "WEB_SEARCH_OK", "SYSTEM", f"Scraped {len(results)} articles for '{query}'")
        return news_block
    except Exception as e:
        logger.log_event("ERROR", "WEB_SEARCH_FAIL", "SYSTEM", str(e))
        return "Live search currently unavailable."

if __name__ == "__main__":
    # A quick local test if we run this file directly
    print("Testing Web Search Engine...\n")
    print(search_breaking_news("S&P 500 Market", 2))
