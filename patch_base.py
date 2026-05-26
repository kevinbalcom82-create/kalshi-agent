import os

file_path = os.path.expanduser("~/kalshi_agent/strategies/base_strategy.py")
with open(file_path, 'r') as f:
    content = f.read()

if "EXECUTION_MODE" in content:
    print("⚠️ Ghost Book is already injected into base_strategy.py!")
else:
    with open(file_path, 'r') as f:
        lines = f.readlines()
        
    with open(file_path, 'w') as f:
        for line in lines:
            if "result = execute_trade(kelly, exact_ticker)" in line:
                indent = line.split("result")[0]
                f.write(indent + "import os\n")
                f.write(indent + "from dotenv import load_dotenv\n")
                f.write(indent + "load_dotenv()\n")
                f.write(indent + "if os.getenv('EXECUTION_MODE', 'LIVE').upper() == 'PAPER':\n")
                f.write(indent + "    from engine.ghost_book import execute_paper_trade\n")
                f.write(indent + "    reasoning = signal.get('audit_notes', signal.get('reasoning', 'Paper trade simulated.'))\n")
                f.write(indent + "    edge = signal.get('edge_source', 'UNKNOWN')\n")
                f.write(indent + "    success = execute_paper_trade(self.name, exact_ticker, kelly['side'], signal['confidence'], float(fresh_price), kelly['contracts'], edge, reasoning)\n")
                f.write(indent + "    if success:\n")
                f.write(indent + "        logger.log_event('INFO', 'PAPER_ORDER_SENT', self.name, f'Simulated {kelly[\"contracts\"]} contracts.')\n")
                f.write(indent + "        send_telegram(f'👻 *{self.name} PAPER STRIKE*\\nSide: {kelly[\"side\"]}\\nContracts: {kelly[\"contracts\"]}\\nEntry: ${fresh_price}')\n")
                f.write(indent + "    else:\n")
                f.write(indent + "        release_fn(position)\n")
                f.write(indent + "else:\n")
                f.write(indent + "    result = execute_trade(kelly, exact_ticker)\n")
            elif "invalidate_cache(self.ticker_prefix)" in line or "ORDER_SENT" in line or "✅ *" in line:
                f.write("    " + line)
            else:
                f.write(line)
    print("✅ Base Strategy Patched! Ghost Book router injected.")
