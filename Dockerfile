FROM python:3.10-slim

# ============================================================================
# ⚠️ SECURITY WARNING - HTTP MODE (STREAMABLE HTTP)
# ============================================================================
# This Docker image runs the MCP server in HTTP mode which has NO authentication.
# The HTTP endpoint is completely unauthenticated - anyone who can reach it can
# execute commands on your Proxmox infrastructure.
#
# CRITICAL SECURITY REQUIREMENTS:
# - NEVER expose this directly to the internet
# - Only bind to localhost (127.0.0.1) or use firewall rules
# - Deploy behind reverse proxy with authentication (nginx, Caddy, OAuth2)
# - Use VPN or SSH tunneling for remote access
# - Implement network-level security (VPC, security groups, etc.)
#
# See README.md "Option C: Docker with HTTP Transport" for full security guide.
# ============================================================================

# Set working directory
WORKDIR /app

# Install uv for PEP 723 dependency management
RUN pip install --no-cache-dir uv

# Copy MCP server script
COPY proxmox_mcp.py .

# Expose HTTP port
EXPOSE 8000

# Health check endpoint (HTTP transport provides /health)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run MCP server in HTTP mode (FastMCP 2.x Streamable HTTP transport)
# WARNING: This mode has NO built-in authentication!
CMD ["uv", "run", "proxmox_mcp.py", "--http", "--port", "8000"]
