#!/usr/bin/env bash
set -e

pip install -r requirements.txt

# Verify the script imports cleanly and CLI is functional (no destructive action)
python -c "import delete_old_traces"
python delete_old_traces.py --help
