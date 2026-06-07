#!/bin/bash
echo "⚡ Powering up Suncoast Agent Factory (Optimized)..."

# AI Brain (Ollama) - FORCED AGGRESSIVE MEMORY FLUSH (15 seconds)
tmux new-session -d -s ai_brain "OLLAMA_KEEP_ALIVE=15s ollama serve"

# PIXEL Ingest Engine (THE BRAIN)
tmux new-session -d -s ingest "source .venv/bin/activate && python3 pixel_ingest.py"

# Private UI Dashboard (Port 8501)
tmux new-session -d -s ui "source .venv/bin/activate && streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0 --server.enableCORS false --server.enableXsrfProtection false"

# Public Funnel (Port 8505)
tmux new-session -d -s public "source .venv/bin/activate && streamlit run funnel.py --server.port 8505 --server.address 0.0.0.0"

# The Harvester (Self-Healing - 5 Minute Cycle)
tmux new-session -d -s harvester "source .venv/bin/activate && while true; do python3 -u daily_harvester.py; sleep 300; done"

# The Engine (Self-Healing - 5 Minute Cycle)
tmux new-session -d -s engine "source .venv/bin/activate && while true; do python3 -u core_engine.py; sleep 300; done"

# Cloudflare Tunnel
tmux new-session -d -s tunnel "cloudflared --config /Users/npcforge/.cloudflared/config.yml tunnel run ai-funnel"

echo "✅ All 7 microservices are ONLINE."
