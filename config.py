"""
Configuration constants for MudaleTunnel.
All magic numbers and configurable values are defined here.
"""
import os

# Port Configuration
DEFAULT_WEB_PORT = int(os.getenv("MUDALETUNNEL_WEB_PORT", "8000"))
DEFAULT_WEB_HOST = os.getenv("MUDALETUNNEL_WEB_HOST", "127.0.0.1")
DEFAULT_FREE_PORT_START = int(os.getenv("MUDALETUNNEL_FREE_PORT_START", "8000"))

# SOCKS Proxy Ports (tried in order)
DEFAULT_SOCKS_PORTS = [1080, 8080, 9050]
SOCKS_PORT_START = 1080

# SSH Configuration
SSH_STARTUP_DELAY = float(os.getenv("MUDALETUNNEL_SSH_DELAY", "0.5"))  # seconds to wait for SSH process startup
SSH_PROCESS_TIMEOUT = int(os.getenv("MUDALETUNNEL_SSH_TIMEOUT", "5"))  # seconds to wait for process termination

# Nmap Configuration
NMAP_SCAN_TIMEOUT = int(os.getenv("MUDALETUNNEL_NMAP_TIMEOUT", "300"))  # seconds
NMAP_DNS_SERVER = "8.8.8.8"
NMAP_DNS_PORT = 53

# Logging Configuration
MAX_LOG_ENTRIES_PER_TUNNEL = int(os.getenv("MUDALETUNNEL_MAX_LOGS", "1000"))
DEFAULT_LOG_LIMIT = int(os.getenv("MUDALETUNNEL_LOG_LIMIT", "100"))

# WebSocket Configuration
WEBSOCKET_PING_INTERVAL = int(os.getenv("MUDALETUNNEL_WS_PING", "30"))  # seconds
WEBSOCKET_TIMEOUT = int(os.getenv("MUDALETUNNEL_WS_TIMEOUT", "30"))  # seconds

# Performance Configuration
PORT_CHECK_CACHE_TTL = float(os.getenv("MUDALETUNNEL_PORT_CACHE_TTL", "1.0"))  # seconds to cache port availability
PORT_CHECK_TIMEOUT = float(os.getenv("MUDALETUNNEL_PORT_TIMEOUT", "0.1"))  # seconds for socket timeout during port check
MAX_CONCURRENT_TUNNELS = int(os.getenv("MUDALETUNNEL_MAX_TUNNELS", "100"))
MAX_PORT_SEARCH_ATTEMPTS = int(os.getenv("MUDALETUNNEL_MAX_PORT_SEARCH", "1000"))  # Max attempts to find free port

# Health Check Configuration
HEALTH_CHECK_INTERVAL = int(os.getenv("MUDALETUNNEL_HEALTH_INTERVAL", "30"))  # seconds between health checks
