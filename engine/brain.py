import os, json, re, requests
from dotenv import load_dotenv
from config import cfg
from output.agent_logger import logger

load_dotenv()

try:
    from engine.memory import recall_memory, format_memories_for_prompt, save_memory
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False
    def recall_memory(*a, **kw): return []
    def format_memories_for_prompt(*a): return ""
    def save_memory(*a, **kw): pass

def generate_signal(context: dict = None):
    context = context or {}
    ticker = context.get("ticker", "UNKNOWN")
    strategy_name = context.get("strategy_name", "UNKNOWN")
    MODEL_NAME = "deepseek-r1:8b"

    memory_block = ""
    if MEMORY_AVAILABLE and strategy_name != "UNKNOWN":
        try:
            memories = recall_memory(strategy_name=strategy_name, current_context=context, n_results=3)
            if memories: memory_block = format_memories_for_prompt(memories)
        except Exception as e:
            logger.log_event("WARNING", "MEMORY_RECALL_SKIP", ticker, str(e))

    base_prompt = context.get("prompt", "")
    if memory_block:
        if "## REQUIRED OUTPUT" in base_prompt: augmented_prompt = base_prompt.replace("## REQUIRED OUTPUT", f"{memory_block}\n## REQUIRED OUTPUT")
        else: augmented_prompt = f"{memory_block}\n\n{base_prompt}"
    else: augmented_prompt = base_prompt

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
    "You must output ONLY raw minified JSON with no commentary."
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
