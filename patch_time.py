import os

file_path = os.path.expanduser("~/kalshi_agent/engine/morning_briefing.py")
with open(file_path, 'r') as f:
    content = f.read()

content = content.replace("from datetime import datetime, timedelta", "from datetime import datetime, timedelta, timezone")
content = content.replace("datetime.utcnow()", "datetime.now(timezone.utc)")

with open(file_path, 'w') as f:
    f.write(content)

print("✅ Timezone logic updated to modern Python standards!")
