"""
memory.py
Kalshi Agent v3.0 — Vector Memory Layer
Uses ChromaDB + nomic-embed-text (local Ollama) to store and recall
past trade setups as semantic memories.

HOW IT WORKS:
  1. After a trade settles, save_memory() stores the full context + outcome
  2. Before the next trade, recall_memory() finds the 3 most similar past setups
  3. format_memories_for_prompt() injects them into the LLM prompt
  4. The agent learns from its own history without retraining

REQUIRES: pip install chromadb
          ollama pull nomic-embed-text
"""
import threading
import hashlib
import time
from datetime import datetime
from typing import Optional

try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, l, e, t, m): print(f"[{l}] {e} | {t} | {m}")
    logger = _FallbackLogger()

import os
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_PATH   = os.path.join(_PROJECT_ROOT, "output", "chromadb")

_client      = None
_client_lock = threading.Lock()


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not CHROMA_AVAILABLE:
        return None
    with _client_lock:
        if _client is None:
            try:
                _client = chromadb.PersistentClient(
                    path=CHROMA_PATH,
                    settings=Settings(
                        anonymized_telemetry=False,
                        allow_reset=True
                    )
                )
                logger.log_event("INFO", "MEMORY_INIT", "SYSTEM",
                                 f"ChromaDB initialized at {CHROMA_PATH}")
            except Exception as e:
                logger.log_event("ERROR", "MEMORY_INIT_FAIL", "SYSTEM", str(e))
                return None
    return _client


def _get_collection(strategy_name: str):
    """Gets or creates a per-strategy ChromaDB collection."""
    client = _get_client()
    if not client:
        return None

    # Use local Ollama embedding model — no API key, no cost
    ollama_ef = embedding_functions.OllamaEmbeddingFunction(
        url="http://localhost:11434/api/embeddings",
        model_name="nomic-embed-text",
    )

    try:
        return client.get_or_create_collection(
            name=f"strategy_{strategy_name.lower().replace(' ', '_')}",
            metadata={"hnsw:space": "cosine"},
            embedding_function=ollama_ef
        )
    except Exception as e:
        logger.log_event("ERROR", "MEMORY_COLLECTION_FAIL", strategy_name, str(e))
        return None


def _build_memory_text(market_context: dict, ai_reasoning: str) -> str:
    """Builds the text string that gets embedded and stored/searched."""
    parts = [
        f"Strategy: {market_context.get('ticker', 'UNKNOWN')}",
        f"Signal: {market_context.get('signal', '')}",
        f"Confidence: {market_context.get('confidence', '')}%",
        f"Edge Source: {market_context.get('edge_source', '')}",
        f"Risk Flag: {market_context.get('risk_flag', '')}",
    ]
    if market_context.get("mom_analysis"):
        parts.append(
            f"MoM Trend: {market_context['mom_analysis'].get('trend_direction', '')}"
        )
    if ai_reasoning:
        parts.append(f"Reasoning: {ai_reasoning}")
    return " | ".join(filter(None, parts))


def save_memory(
    strategy_name: str,
    market_context: dict,
    ai_reasoning: str,
    outcome: str,
    settled_value: Optional[str] = None,
    signal_id: Optional[int] = None
) -> None:
    """
    Saves a completed trade to vector memory.
    Runs in a background thread — never blocks the main engine.
    Call this after a trade settles (WIN/LOSS confirmed).
    """
    def _write():
        collection = _get_collection(strategy_name)
        if not collection:
            return
        try:
            memory_text = _build_memory_text(market_context, ai_reasoning)
            raw_id      = f"{strategy_name}_{market_context.get('ticker', '')}_{time.time()}"
            doc_id      = hashlib.md5(raw_id.encode()).hexdigest()

            metadata = {
                "strategy":      strategy_name,
                "ticker":        str(market_context.get("ticker", "")),
                "signal":        str(market_context.get("signal", "")),
                "confidence":    int(market_context.get("confidence", 0)),
                "outcome":       outcome,
                "settled_value": str(settled_value or ""),
                "signal_id":     int(signal_id or 0),
                "timestamp":     datetime.utcnow().isoformat(),
                "edge_source":   str(market_context.get("edge_source", "")),
                "risk_flag":     str(market_context.get("risk_flag", "")),
            }

            collection.add(
                documents=[memory_text],
                metadatas=[metadata],
                ids=[doc_id]
            )
            logger.log_event("INFO", "MEMORY_SAVED", strategy_name,
                             f"Outcome: {outcome} | ID: {doc_id[:8]}")
        except Exception as e:
            logger.log_event("ERROR", "MEMORY_SAVE_FAIL", strategy_name, str(e))

    threading.Thread(target=_write, daemon=True).start()


def recall_memory(
    strategy_name: str,
    current_context: dict,
    n_results: int = 3,
    outcome_filter: Optional[str] = None
) -> list[dict]:
    """
    Finds the N most similar past trade setups using cosine similarity.
    Call this in build_context() before assembling the prompt.

    outcome_filter: pass "WIN" to only recall winning setups,
                    "LOSS" to only recall losing ones, or None for both.
    """
    collection = _get_collection(strategy_name)
    if not collection:
        return []

    try:
        query_text = _build_memory_text(current_context, "")
        count      = collection.count()
        if count == 0:
            return []

        query_kwargs = {
            "query_texts": [query_text],
            "n_results":   min(n_results, count),
            "include":     ["documents", "metadatas", "distances"]
        }
        if outcome_filter:
            query_kwargs["where"] = {"outcome": outcome_filter}

        results   = collection.query(**query_kwargs)
        memories  = []

        documents = results.get("documents") or []
        metadatas = results.get("metadatas") or []
        distances = results.get("distances") or []

        if not documents or not metadatas or not distances:
            return []

        for doc, meta, dist in zip(documents[0], metadatas[0], distances[0]):
            similarity = round((1 - (dist / 2)) * 100, 1)
            memories.append({
                "reasoning":     doc,
                "outcome":       meta.get("outcome", "UNKNOWN"),
                "confidence":    meta.get("confidence", 0),
                "settled_value": meta.get("settled_value", ""),
                "edge_source":   meta.get("edge_source", ""),
                "risk_flag":     meta.get("risk_flag", ""),
                "timestamp":     meta.get("timestamp", ""),
                "similarity_pct": similarity
            })

        logger.log_event(
            "INFO", "MEMORY_RECALL", strategy_name,
            f"Found {len(memories)} similar setups" if memories else "No matches"
        )
        return memories

    except Exception as e:
        logger.log_event("ERROR", "MEMORY_RECALL_FAIL", strategy_name, str(e))
        return []


def format_memories_for_prompt(memories: list[dict]) -> str:
    """
    Formats recalled memories into a prompt block ready to inject
    into any strategy's build_context() prompt_sections list.
    """
    if not memories:
        return ""

    lines = [
        "## HISTORICAL MEMORY (Similar Past Setups)\n",
        "Study these past setups carefully. "
        "Avoid repeating strategies that led to LOSS outcomes.\n"
    ]

    for i, mem in enumerate(memories, 1):
        outcome_emoji = (
            "✅" if mem["outcome"] == "WIN"  else
            "❌" if mem["outcome"] == "LOSS" else "⏳"
        )
        lines.append(
            f"Memory {i} ({mem['similarity_pct']}% similar) "
            f"{outcome_emoji} {mem['outcome']}\n"
            f"  Context: {mem['reasoning'][:200]}\n"
            f"  Settled: {mem['settled_value']} | "
            f"Confidence was: {mem['confidence']}% | "
            f"Edge: {mem['edge_source']}\n"
        )

    return "\n".join(lines)


def inject_lesson(
    strategy_name: str,
    lesson: str,
    source_signal_id: int
) -> None:
    """
    Stores a lesson extracted by self_improver.py into memory.
    These lessons are tagged as LESSON type so they can be filtered
    separately from regular trade memories if needed.
    """
    def _write():
        collection = _get_collection(strategy_name)
        if not collection:
            return
        try:
            doc_id = hashlib.md5(
                f"lesson_{strategy_name}_{source_signal_id}".encode()
            ).hexdigest()

            collection.add(
                documents=[f"LESSON LEARNED: {lesson}"],
                metadatas=[{
                    "strategy":      strategy_name,
                    "ticker":        "LESSON",
                    "signal":        "LESSON",
                    "confidence":    0,
                    "outcome":       "LESSON",
                    "signal_id":     source_signal_id,
                    "timestamp":     datetime.utcnow().isoformat(),
                    "edge_source":   "SELF_IMPROVEMENT",
                    "risk_flag":     "LOW",
                    "settled_value": ""
                }],
                ids=[doc_id]
            )
            logger.log_event("INFO", "LESSON_INJECTED", strategy_name,
                             "Lesson stored in vector memory.")
        except Exception as e:
            logger.log_event("ERROR", "LESSON_INJECT_FAIL", strategy_name, str(e))

    threading.Thread(target=_write, daemon=True).start()
