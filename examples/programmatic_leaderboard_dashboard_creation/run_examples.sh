#!/usr/bin/env bash
set -e

pip install -r requirements.txt

# Run experiments (heuristic scoring only — no LLM API key required)
python run_experiments.py --output ci_leaderboard_config.yaml

# Create the leaderboard dashboard from the generated config
python create_leaderboard_from_yaml.py --config ci_leaderboard_config.yaml --replace
