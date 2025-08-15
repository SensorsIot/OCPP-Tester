"""
Centralized configuration for the OCPP server app.
Values can be overridden via environment variables.
"""
import os

def _env(name: str, default: str) -> str:
    return os.getenv(name, default)

# --- OCPP / WebSockets ---
OCPP_HOST = _env("OCPP_HOST", "0.0.0.0")
OCPP_PORT = int(_env("OCPP_PORT", "8887"))

# Paths on the same OCPP_PORT (one server with a path router).
LOG_WS_PATH = _env("LOG_WS_PATH", "/logs")
EV_STATUS_WS_PATH = _env("EV_STATUS_WS_PATH", "/ev-status")

# --- HTTP (Flask via uvicorn) ---
HTTP_HOST = _env("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(_env("HTTP_PORT", "5000"))

# Where to find the UI index.html (absolute or relative)
UI_INDEX_PATH = _env("UI_INDEX_PATH", "app/templates/index.html")

# --- EV Simulator ---
EV_SIMULATOR_BASE_URL = _env("EV_SIMULATOR_BASE_URL", "http://192.168.0.151")
EV_STATUS_POLL_INTERVAL = int(_env("EV_STATUS_POLL_INTERVAL", "5"))  # seconds
EV_WAIT_MAX_BACKOFF = int(_env("EV_WAIT_MAX_BACKOFF", "30"))         # seconds
