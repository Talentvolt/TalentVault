# Gunicorn configuration file
import os

# Set timeout to 120 seconds for processing LLM completions
timeout = 120

# Bind to the PORT environment variable provided by Render, defaulting to 10000
port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"

# Preload app to save memory
preload_app = True

# Access log format
accesslog = "-"
