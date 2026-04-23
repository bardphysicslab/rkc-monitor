#!/usr/bin/env bash
set -euo pipefail

python3 -m venv raspi/venv
source raspi/venv/bin/activate
pip install -r requirements.txt
mkdir -p data

echo "Pi setup complete."
echo "Next steps:"
echo "  1. Edit raspi/config/app_config.example.json or point BARDBOX_APP_CONFIG at a real config."
echo "  2. Run from repo root: uvicorn raspi.main:app --host 0.0.0.0 --port 8000"
echo "  3. Create a systemd service once the deployment is ready."
