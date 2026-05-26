import os, json, re, requests
from dotenv import load_dotenv
from config import cfg
from output.agent_logger import logger
from datetime import datetime

load_dotenv()

try:
    from engine.memory import recall_memory, format_memories_for_prompt, save_memory
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False
    def recall_memory(*a, **kw): return []
    def format_memories_for_prompt(*a): return ""
    def save_memory(*a, **kw): pass

try:
    from engine.web_tools import search_breaking_news
    WEB_AVAILABLE = True
except ImportError:
    WEB_AVAILABLE = False

def generate_signal(context: dict = None):
    context = context or {}
    ticker = context.get("ticker", "UNKNOWN")
    strategy_name = context.get("strategy_name", "UNKNOWN")
    MODEL_NAME = "deepseek-r1:8b"

    # 1. Pull Historical Memory
    memory_block = ""
    if MEMORY_AVAILABLE and strategy_name != "UNKNOWN":
        try:
            memories = recall_memory(strategy_name=strategy_name, current_context=context, n_results=3)
            if memories: memory_block = format_memories_for_prompt(memories)
        except Exception as e:
            logger.log_event("WARNING", "MEMORY_RECALL_SKIP", ticker, str(e))

    # 2. Pull Live Breaking News
    news_block = ""
    if WEB_AVAILABLE and ticker != "UNKNOWN":
        search_term = ticker.replace("KXINTRADAY", "S&P 500").replace("KXNBA", "NBA")
        news_block = search_breaking_news(f"{search_term} market", max_results=2)

    # 3. Assemble the Hybrid Prompt
    base_prompt = context.get("prompt", "")
    
    injections = []
    if news_block and "No recent" not in news_block: injections.append(news_block)
    if memory_block: injections.append(memory_block)
    injection_text = "\n\n".join(injections)

    if injection_text:
        if "## REQUIRED OUTPUT" in base_prompt: 
            augmented_prompt = base_prompt.replace("## REQUIRED OUTPUT", f"{injection_text}\n## REQUIRED OUTPUT")
        else: 
            augmented_prompt = f"{injection_text}\n\n{base_prompt}"
    else: 
        augmented_prompt = base_prompt

    system_prompt = (
        "You are the Chief Risk Officer (CRO) of a delta-neutral quantitative fund. "
        "Your mandate is strict capital preservation above all else. "
        "View every market setup with extreme skepticism — your default answer is WATCH. "
        "If historical memory shows a similar setup resulted in LOSS, you must output WATCH "
        "regardless of current signals. "
        "Confidence must reflect actual data strength: "
        "use 90+ only with extreme alignment, 75-89 for clear edge, "
        "65-74 for uncertainty, below 65 output WATCH. "
        "Never default to 75 — that is a sign of lazy calibration. "
        "CRITICAL INSTRUCTION: You must output ONLY a valid JSON object matching this exact schema. "
        "Do not include markdown formatting, backticks, or conversational text. "
        "{"
        '  "signal": "BUY" or "WATCH",'
        '  "direction": "yes" or "no",'
        '  "confidence": <float between 0 and 100>,'
        '  "reasoning": "<short string explaining your logic>"'
        "}"
    )
    user_prompt = f"TARGET TICKER: {ticker}\nCONTEXT & RULES:\n{augmented_prompt}"

    try:
        url = "http://localhost:11434/api/chat"
        payload = {"model": MODEL_NAME, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "stream": False, "options": {"temperature": 0.6, "num_predict": 2500}}
        response = requests.post(url, json=payload, timeout=180).json()
        message = response.get("message", {})
        reasoning_log = message.get("thinking", message.get("reasoning", ""))
        raw_text = message.get("content", "")
        if not raw_text.strip(): raw_text = message.get("thinking", message.get("reasoning", ""))
        raw_text = re.sub(r"//[^\n]*", "", raw_text)
        raw_text = re.sub(r"/\*.*?\*/", "", raw_text)
        if "<think>" in raw_text:
            parts = raw_text.split("</think>")
            reasoning_log += "\n" + parts[0].replace("<think>", "").strip()
            raw_text = parts[1] if len(parts) > 1 else raw_text

        # --- RAW BRAIN LOGGER ---
        try:
            log_path = os.path.expanduser("~/kalshi_agent/output/hermes_brain.log")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(f"\n{'='*60}\n")
                lf.write(f"🧠 HERMES RAW COGNITION | {timestamp} | {ticker}\n")
                lf.write(f"STRATEGY: {strategy_name}\n")
                lf.write(f"{'-'*60}\n")
                lf.write(f"📥 INJECTED CONTEXT & DATA:\n{user_prompt}\n")
                lf.write(f"{'-'*60}\n")
                lf.write(f"📤 AI INTERNAL MONOLOGUE (<think>):\n{reasoning_log.strip()}\n")
                lf.write(f"📤 FINAL JSON OUTPUT:\n{raw_text.strip()}\n")
                lf.write(f"{'='*60}\n")
        except Exception as log_err:
            logger.log_event("ERROR", "LOGGER_FAIL", ticker, str(log_err))
        # ------------------------

        json_match = re.search(r'\{.*?\}', raw_text, re.DOTALL)
        if not json_match: raise ValueError("No JSON block found in content.")
        signal = json.loads(json_match.group(0))
        signal["reasoning_log"] = reasoning_log.strip()
        signal["memory_used"] = bool(memory_block)

        if "direction" not in signal and "signal" in signal:
            sig_val = signal.get("signal", "")
            if "YES" in sig_val: signal["direction"] = "yes"
            elif "NO" in sig_val: signal["direction"] = "no"
            else: signal["direction"] = "no"

        if MEMORY_AVAILABLE and strategy_name != "UNKNOWN":
            save_memory(strategy_name=strategy_name, market_context={**context, **signal}, ai_reasoning=signal.get("reasoning", ""), outcome="PENDING")

        return signal
    except Exception as e:
        logger.log_event("ERROR", "LOCAL_BRAIN_FAIL", ticker, str(e))
        return {"direction": "no", "confidence": 0.0, "reasoning": f"Error: {str(e)}", "reasoning_log": str(e), "memory_used": False}
