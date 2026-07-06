# Gunicorn configuration file
import os

# Set timeout to 120 seconds for processing LLM completions
timeout = 120

# Bind to the PORT environment variable provided by Render, defaulting to 10000
port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"

# Do not preload app to avoid port binding delays and prevent db connection sharing issues
preload_app = False

# Access log format
accesslog = "-"
