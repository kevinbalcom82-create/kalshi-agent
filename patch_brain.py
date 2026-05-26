import os

file_path = os.path.expanduser("~/kalshi_agent/engine/brain.py")

with open(file_path, "r") as f:
    content = f.read()

# 1. Add the memory imports at the top
if "from engine.memory import" not in content:
    content = content.replace(
        "import requests, json", 
        "import requests, json\ntry:\n    from engine.memory import recall_memory, format_memories_for_prompt\n    MEMORY_AVAILABLE = True\nexcept ImportError:\n    MEMORY_AVAILABLE = False"
    )

# 2. Inject memory into the prompt builder
if "MEMORY_AVAILABLE" in content and "memory_block =" not in content:
    old_prompt_code = 'prompt = f"## TICKER: {ticker}\\n## DATA:\\n{context}"'
    new_prompt_code = '''memory_block = ""
    if MEMORY_AVAILABLE:
        past_memories = recall_memory(strategy_name, context, n_results=3)
        memory_block = format_memories_for_prompt(past_memories)
        
    prompt = f"## TICKER: {ticker}\\n## DATA:\\n{context}\\n\\n{memory_block}"'''
    
    # We will just do a blind replace of where the user prompt is built
    content = content.replace('    prompt = f"', '    memory_block = ""\n    if MEMORY_AVAILABLE:\n        past_memories = recall_memory("GENERAL", context, n_results=3)\n        memory_block = format_memories_for_prompt(past_memories)\n\n    prompt = f"## PAST LESSONS:\\n{memory_block}\\n\\n')

with open(file_path, "w") as f:
    f.write(content)

print("✅ Brain patched with Hybrid Memory Loop!")
