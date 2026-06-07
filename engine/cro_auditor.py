from decimal import Decimal
from typing import Optional

def get_macro_context():
    return {}

def audit_signal(raw_signal: dict, context: Optional[dict] = None) -> dict:
    if context is None:
        context = get_macro_context()

    audited = raw_signal.copy()
    audited["veto"] = False
    notes = []

    signal_type = audited.get("signal", "WATCH").upper()
    direction   = audited.get("direction", "").lower()
    confidence  = audited.get("confidence", 0)

    bls_history = context.get("bls_history", [])
    if len(bls_history) >= 2:
        try:
            bls_latest = Decimal(str(bls_history[0].get("value", "0")))
            bls_prev   = Decimal(str(bls_history[1].get("value", "0")))
            if bls_latest > bls_prev and direction == "no":
                audited["veto"] = True
                notes.append("Rule 6: BLS rising — vetoing BEARISH signal.")
        except Exception:
            pass

    is_fomc = context.get("is_fomc_today", False)
    if is_fomc and signal_type != "WATCH":
        audited["risk_flag"] = "HIGH"
        notes.append("Rule 7: FOMC day — risk elevated to HIGH.")

    yield_trend = context.get("yield_trend", "NEUTRAL").upper()
    tone_label  = context.get("tone_label", "NEUTRAL").upper()
    conflicting = (
        (yield_trend == "RISING"  and tone_label == "DOVISH") or
        (yield_trend == "FALLING" and tone_label == "HAWKISH")
    )
    if conflicting:
        confidence = min(confidence, 65)
        audited["confidence"] = confidence
        notes.append("Rule 8: Yield/tone conflict — confidence capped at 65.")

    try:
        entry = Decimal(str(audited.get("suggested_entry_dollars", "0")))
        if entry > Decimal("0.85"):
            audited["signal"] = "WATCH"
            notes.append("Rule 4: Entry > 0.85 — forced WATCH.")
    except Exception:
        pass

    if confidence < 65:
        audited["signal"] = "WATCH"
        notes.append(f"Rule 5: Confidence {confidence}% below floor.")

    audited["audit_notes"] = " | ".join(notes) if notes else "Passed Deterministic Audit."
    return audited
