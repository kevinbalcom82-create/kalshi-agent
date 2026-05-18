"""
kelly_sizer.py - Risk Management & Position Sizing
Applies 1/4 Kelly Criterion with a strict 15% bankroll cap.
"""
from decimal import Decimal

def calculate_kelly(bankroll: Decimal, confidence: Decimal, entry_price: Decimal) -> dict:
    # Convert AI confidence (e.g., 65) to probability (0.65)
    # Note: If your AI already outputs 0.65, remove the division by 100 here.
    p = confidence / Decimal("100") 
    q = Decimal("1") - p
    
    if entry_price <= Decimal("0") or entry_price >= Decimal("1"):
        return {"contracts": 0, "size": "0", "veto": True, "reason": "Invalid entry price"}
        
    # Decimal odds (profit per $1 wagered)
    b = (Decimal("1") - entry_price) / entry_price
    
    # f* = (bp - q) / b
    f = (p * b - q) / b
    
    if f <= Decimal("0"):
        return {"contracts": 0, "size": "0", "veto": True, "reason": "Negative statistical edge"}
        
    # Variance smoothing (1/4 Kelly)
    fractional_kelly = f / Decimal("4")
    
    # Hard risk limits
    max_cap = Decimal("0.15")
    final_f = min(fractional_kelly, max_cap)
    
    allocated_capital = bankroll * final_f
    contracts = int(allocated_capital / entry_price)
    
    return {
        "contracts": contracts,
        "capital_at_risk": str(allocated_capital),
        "fraction_used": str(final_f),
        "veto": False
    }
