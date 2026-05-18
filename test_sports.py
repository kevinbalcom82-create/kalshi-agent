import sys
sys.path.append('.')
from strategies.sports_sniper import SportsSniperEdge

s = SportsSniperEdge()
print('Name:', s.name)
print('Ticker:', s.ticker_prefix)
print('Active today:', s.is_active_today())
ctx = s.build_context()
print('Context keys:', list(ctx.keys()))
print('Prompt length:', len(ctx.get('prompt', '')))
