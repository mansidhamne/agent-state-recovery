#!/usr/bin/env bash
# Run on a fresh Ubuntu 24.04 instance, from the repo root (doc section 16.2).
# The API key is not set here. Put it in ~/.mccr_env with chmod 600.
set -euo pipefail

sudo apt-get update
sudo apt-get install -y python3.12-venv git tmux awscli
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
