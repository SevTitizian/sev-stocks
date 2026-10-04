#!/bin/zsh
# Start the dashboard. Creates the virtual environment on first run.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
fi
.venv/bin/streamlit run app.py
