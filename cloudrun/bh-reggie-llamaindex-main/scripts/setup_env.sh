#!/bin/bash

# Create and activate virtual environment
python3 -m venv llama_env
source llama_env/bin/activate

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt

echo "✅ Environment setup complete. Virtual environment 'llama_env' is active."
