"""
brain.py - Local Reasoning Mode (Agnostic JSON parsing)
"""
import os
import json
from dotenv import load_dotenv
from config import cfg
from output.agent_logger import logger
import re
import requests

load_dotenv()

def generate_signal(context: dict = None):
    context = context or {}
    ticker = context.get("ticker", "UNKNOWN")
    MODEL_NAME = "deepseek-r1:8b"

    # Brain is now a dumb pipe. It lets the Strategy dictate the rules.
    system_prompt = "You are an elite quantitative AI. Follow the user's prompt exactly. You must output valid JSON. Do not output markdown outside the JSON."
    user_prompt = f"TARGET TICKER: {ticker}\nCONTEXT & RULES: {json.dumps(context, default=str)}"

    try:
        url = "http://localhost:11434/api/chat"
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.6,
                "num_predict": 2500
            }
        }
        
        response = requests.post(url, json=payload, timeout=180).json()
        message = response.get("message", {})
        
        # Keep X-Ray active for now
        print("\n--- RAW OLLAMA PAYLOAD ---")
        print(message)
        print("--------------------------\n")
        
        # Safely extract thoughts whether Ollama calls it 'thinking' or 'reasoning'
        reasoning_log = message.get("thinking", message.get("reasoning", ""))
        raw_text = message.get("content", "")
        # Fallback: DeepSeek sometimes puts JSON in thinking when content is empty
        if not raw_text.strip():
            raw_text = message.get("thinking", message.get("reasoning", ""))
        
        # Strip JS-style comments DeepSeek adds to JSON

        raw_text = re.sub(r"//[^\n]*", "", raw_text)
        raw_text = re.sub(r"/\*.*?\*/", "", raw_text)
        if "<think>" in raw_text:
            parts = raw_text.split("</think>")
            reasoning_log += "\n" + parts[0].replace("<think>", "").strip()
            raw_text = parts[1] if len(parts) > 1 else raw_text

        json_match = re.search(r'\{.*?\}', raw_text, re.DOTALL)
        if not json_match:
            raise ValueError(f"No JSON block found in content.")
            
        signal = json.loads(json_match.group(0))
        signal["reasoning_log"] = reasoning_log.strip()
        
        # Safety net: If the strategy uses 'signal' (like Equities) instead of 'direction', map it.
        if "direction" not in signal and "signal" in signal:
            sig_val = signal.get("signal", "")
            if "YES" in sig_val: signal["direction"] = "yes"
            elif "NO" in sig_val: signal["direction"] = "no"
            else: signal["direction"] = "no"
            
        return signal

    except Exception as e:
        logger.log_event("ERROR", "LOCAL_BRAIN_FAIL", ticker, str(e))
        return {"direction": "no", "confidence": 0.0, "reasoning": "Error", "reasoning_log": str(e)}

if __name__ == "__main__":
    print(f"[*] Testing Agnostic Local Brain...")
    sig = generate_signal({"ticker": "TEST", "prompt": "Output JSON with direction: yes"})
    print(sig)
