#!/bin/bash
echo "Starting ThinkVelocity..."
echo "Model: $LLM_MODEL"
uvicorn main:app --reload --host 0.0.0.0 --port 8000
