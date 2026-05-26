import os

file_path = os.path.expanduser("~/kalshi_agent/core_engine.py")
with open(file_path, 'r') as f:
    content = f.read()

if "morning_briefing" not in content:
    content = content.replace("from engine.self_improver import start_nightly_auditor", "from engine.self_improver import start_nightly_auditor\nfrom engine.morning_briefing import generate_and_send_briefing")
    content = content.replace("print(f\"[*] Awaiting Schedule Triggers", "schedule.every().day.at(\"08:00\").do(generate_and_send_briefing)\n    print(f\"[*] Awaiting Schedule Triggers")
    
    with open(file_path, 'w') as f:
        f.write(content)
    print("✅ Executive Briefing scheduled for 08:00 AM daily!")
else:
    print("⚠️ Briefing already scheduled.")
