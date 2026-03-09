#!/bin/sh
set -e

cd /workspace/ics-decision-engine

# Ensure dependencies are up to date on every start
pip install -r requirements.txt --quiet

# Start the FastAPI server on port 8000
uvicorn app:api --host 0.0.0.0 --port 8000 --reload
