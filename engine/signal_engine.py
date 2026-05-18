"""
signal_engine.py
Kalshi Agent v2.4 — Multi-Agent Reasoning Engine
Generates signals via Qwen2.5:7b and validates via Deterministic CRO.
"""

import json
import requests
from config import cfg
from engine.cro_auditor import audit_signal

# Ollama Config
OLLAMA_URL = "http://localhost:11434/api/generate"

def generate_signal(context: dict) -> dict:
    """
    Calls local LLM to generate a trade signal based on provided context.
    Passes result through Deterministic CRO Auditor before returning.
    """
    ticker = context.get("ticker", "UNKNOWN")
    
    payload = {
        "model": "qwen2.5:7b",
        "prompt": context.get("prompt", ""),
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
            "num_predict": 300
        }
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        raw_output = response.json().get("response", "{}")
        data = json.loads(raw_output)
    except Exception as e:
        return {
            "signal": "WATCH",
            "confidence": 0,
            "reasoning": f"Inference Failure: {str(e)}",
            "risk_flag": "HIGH"
        }

    # Integrate Priority 1: Deterministic CRO Audit
    # We pass the LLM data and the original context to the auditor
    audited_data = audit_signal(data, context)
    
    return audited_data
