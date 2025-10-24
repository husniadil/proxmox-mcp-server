# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Proxmox MCP Server is a Model Context Protocol server that enables AI assistants to manage Proxmox LXC containers through SSH. It provides tools to execute commands inside containers, manage container lifecycle (start/stop), and optionally execute commands directly on the Proxmox host.

**Critical Security Feature**: This software requires explicit risk acceptance (`I_ACCEPT_RISKS=true`) before it will run, as it provides SSH access to infrastructure.

## Development Commands

### Testing & Running

```bash
# Test the MCP server directly (using uv - recommended)
uv run proxmox_mcp.py

# Or with traditional Python
python proxmox_mcp.py

# Test SSH connection (requires .env configuration)
ssh root@<HOST>
```

### Configuration Setup

```bash
# Create environment configuration
cp .env.example .env
# Then edit .env with your Proxmox credentials

# Test with Claude Desktop
# Edit ~/Library/Application Support/Claude/claude_desktop_config.json (macOS)
# Or %APPDATA%\Claude\claude_desktop_config.json (Windows)
# Then restart Claude Desktop
```

### Docker Deployment

For production deployment using Docker/HTTP mode, this project includes comprehensive Docker support:

- Docker Compose configuration for easy deployment
- HTTP transport mode with health check endpoint
- Environment variable configuration via `.env` file
- Security considerations for HTTP mode (unauthenticated endpoint)

**See README.md "Option C: Docker with HTTP Transport" for:**
- Complete Docker setup instructions
- Docker Compose usage
- Environment variable configuration
- Health check endpoint details
- Security best practices for HTTP deployment
- Custom port configuration
- Production deployment with Docker secrets

**Note:** HTTP mode is designed for production/remote deployments. For local Claude Desktop use, prefer stdio mode (Options A or B).

## Architecture

### Single-File MCP Server (PEP 723)

This project uses PEP 723 (inline script metadata), meaning all dependencies are declared in the script header (`proxmox_mcp.py`) rather than a separate `requirements.txt`. Dependencies:

- `mcp>=1.0.0` - Model Context Protocol SDK
- `fastmcp>=2.12.5` - FastMCP framework for building MCP servers
- `paramiko>=4.0.0` - SSH client library
- `pydantic>=2.12.3` - Data validation
- `python-dotenv>=1.1.1` - Environment variable management
- `uvicorn>=0.38.0` - ASGI server for HTTP mode

### Connection Architecture

```
Claude Desktop → MCP Server → SSH Connection → Proxmox Host → pct exec → LXC Container
```

The SSH connection is established during server lifecycle (`lifespan` context manager) and maintained throughout the session. All commands are executed through this single SSH connection.

### Key Components

**Configuration (`ProxmoxConfig`)**

- Loads settings from environment variables (.env file)
- Validates required fields (`HOST`, authentication credentials)
- Enforces risk acceptance check (`I_ACCEPT_RISKS=true`)
- Feature flags: `ENABLE_HOST_EXEC` (default: false), `CHARACTER_LIMIT` (default: 25000)
- Max file size configuration via `MAX_FILE_SIZE` environment variable (default: 10MB)
- HTTP server port via `SERVER_PORT` environment variable (default: 8000)

**SSH Connection Manager (`SSHConnectionManager`)**

- Manages Paramiko SSH client lifecycle
- Supports both password and SSH key authentication
- Executes commands via SSH and returns (stdout, stderr, exit_code)
- Provides SFTP client for file transfers
- Connection established in `lifespan` context manager

**Input Validation Models**

- All tool inputs are validated using Pydantic v2 models
- Strict validation: strip whitespace, forbid extra fields, enforce ranges
- `vmid`: Container IDs must be 100-999999999
- `command`: Limited to 10000 characters
- `timeout`: 1-300 seconds
- `response_format`: Either "json" or "text"

### MCP Tools (10 Total)

1. **proxmox_container_exec_command**
   - Executes bash commands inside containers via `pct exec <vmid> -- bash -c '<command>'`
   - Handles command escaping for single quotes
   - Returns output in JSON or text format

2. **proxmox_list_containers**
   - Runs `pct list` to get all containers
   - Parses output into structured data (vmid, status, name)

3. **proxmox_container_status**
   - Runs `pct status <vmid>`
   - Returns: running, stopped, or unknown

4. **proxmox_start_container**
   - Runs `pct start <vmid>`
   - Idempotent (safe to call on already running container)

5. **proxmox_stop_container**
   - Runs `pct stop <vmid>`
   - Idempotent (safe to call on already stopped container)

6. **proxmox_host_exec_command**
   - **DISABLED BY DEFAULT** - requires `ENABLE_HOST_EXEC=true`
   - Executes commands directly on Proxmox host (not in container)
   - Marked as `destructiveHint: True` due to potential infrastructure impact
   - Use for host operations: `pct list`, `pvecm status`, `zpool status`, etc.

7. **proxmox_download_file_from_container**
   - Downloads files from containers to local machine
   - Workflow: `pct pull` to host temp → SFTP download → cleanup temp
   - Validates file size against MAX_FILE_SIZE
   - Includes overwrite protection

8. **proxmox_upload_file_to_container**
   - Uploads files from local machine to containers
   - Workflow: SFTP upload to host temp → `pct push` to container → set permissions → cleanup temp
   - Validates file size, permissions, and paths
   - Checks if file exists before overwriting
   - Marked as `destructiveHint: True`

9. **proxmox_download_file_from_host**
   - Downloads files directly from Proxmox host
   - **Requires ENABLE_HOST_EXEC=true**
   - Direct SFTP download (no staging needed)
   - Validates file size before transfer

10. **proxmox_upload_file_to_host**
   - Uploads files directly to Proxmox host
   - **Requires ENABLE_HOST_EXEC=true**
   - Direct SFTP upload with permission setting
   - Marked as `destructiveHint: True`
   - Includes overwrite protection

### Output Truncation

All command outputs are truncated to `CHARACTER_LIMIT` characters (default: 25000) to prevent token exhaustion. See `truncate_output()` function in the helper functions section.

### HTTP Mode & Health Check

The server supports two transport modes:

1. **Stdio Mode (Default)**: For Claude Desktop integration, communicates via stdin/stdout
2. **HTTP Mode**: For remote access and web integrations, runs as HTTP server

**HTTP Mode Usage:**

```bash
# Start in HTTP mode
python proxmox_mcp.py --http --host 0.0.0.0 --port 8000

# Or with uv
uv run proxmox_mcp.py --http --port 8000
```

**⚠️ SECURITY WARNING - HTTP Mode:**

HTTP mode does **NOT** include any authentication mechanism. The server exposes MCP endpoints without authentication, meaning anyone who can reach the HTTP endpoint can execute commands on your Proxmox infrastructure.

**Security implications:**
- The HTTP endpoint is completely unauthenticated
- Server relies on .env file credentials for Proxmox SSH access only
- No built-in access control or rate limiting
- Anyone with network access can use all MCP tools

**Required security measures:**
- **NEVER** expose HTTP endpoint directly to the internet
- Bind to localhost (127.0.0.1) or use firewall rules to restrict access
- Deploy behind reverse proxy with authentication (nginx, Caddy, etc.)
- Use VPN or SSH tunneling for remote access
- Implement network-level security (VPC, security groups, etc.)
- Monitor access logs regularly

**Recommended deployment patterns:**
1. **Local only**: `--host 127.0.0.1` (accessible only from same machine)
2. **Internal network**: Use firewall to restrict to trusted IP ranges
3. **VPN access**: Expose only through VPN tunnel
4. **Reverse proxy**: Deploy nginx/Caddy with HTTP Basic Auth or OAuth2
5. **SSH tunnel**: `ssh -L 8000:localhost:8000 user@server` for remote access

**Health Check Endpoint:**

When running in HTTP mode, a `/health` endpoint is available for monitoring:

- **URL**: `http://host:port/health`
- **Method**: GET
- **Response**: JSON with server status

```json
{
  "status": "healthy",
  "service": "proxmox-mcp-server",
  "ssh_connected": true
}
```

**Implementation Details:**

- Health check implemented as ASGI middleware in the `health_check_middleware` function
- Intercepts `/health` requests before they reach MCP app
- Checks SSH connection status by verifying `ssh_manager._client` is not None
- All other requests pass through to FastMCP app
- The middleware wraps `mcp.streamable_http_app()` in HTTP mode

**Endpoints:**

- `/health` - Health check (returns JSON status)
- `/mcp` - MCP protocol endpoint (for MCP clients)

## File Transfer Architecture

### Overview

File transfers use a two-step process for containers (via temporary staging on host) and direct SFTP for host operations.

### Container File Transfer Workflow

**Download (Container → Local):**

1. Execute `pct pull <vmid> <container_path> <temp_path>` to copy file from container to host
2. Check file size on host using `stat -c%s <temp_path>`
3. Validate size against `MAX_FILE_SIZE` limit
4. Use SFTP to download from `<temp_path>` to local machine
5. Clean up `<temp_path>` on host (even on errors)

**Upload (Local → Container):**

1. Validate local file exists and size is within MAX_FILE_SIZE
2. Check if container file exists (unless overwrite=true)
3. Use SFTP to upload from local to host `<temp_path>`
4. Execute `pct push <vmid> <temp_path> <container_path>` to copy to container
5. Execute `pct exec <vmid> -- chmod <permissions> <container_path>` to set permissions
6. Clean up `<temp_path>` on host (even on errors)

**Temp File Management:**

- Temp paths generated via `get_temp_path()` using UUID: `/tmp/proxmox-mcp-{uuid}`
- Cleanup handled by `SSHConnectionManager.cleanup_remote_file()` method
- Try/finally blocks ensure cleanup even on errors in all file transfer functions

### Host File Transfer Workflow

**Download (Host → Local):**

1. Check `ENABLE_HOST_EXEC` flag
2. Execute `stat -c%s <host_path>` to get file size
3. Validate size against MAX_FILE_SIZE
4. Use SFTP to download directly from host to local
5. No temp files needed

**Upload (Local → Host):**

1. Check `ENABLE_HOST_EXEC` flag
2. Validate local file exists and size
3. Check if host file exists (unless overwrite=true)
4. Use SFTP to upload directly from local to host
5. Execute `chmod <permissions> <host_path>` to set permissions
6. No temp files needed

### SFTP Integration

**SSHConnectionManager Extensions:**

- `_sftp: Optional[paramiko.SFTPClient]` - SFTP client instance
- `get_sftp_client()` - Creates/returns SFTP client (lazy initialization)
- `download_file(remote_path, local_path)` - SFTP download wrapper
- `upload_file(local_path, remote_path)` - SFTP upload wrapper
- `cleanup_remote_file(remote_path)` - Safe file removal (ignores errors)
- `execute_command(command, timeout)` - Core SSH command execution
- `disconnect()` - Closes SFTP client before SSH client

### Security Validations

**Path Validation (validate_path function):**

- Checks for empty paths
- Prevents directory traversal (rejects paths with `..`)
- Enforces max path length of 4096 characters

**Permission Validation (validate_permissions function):**

- Validates octal format using regex `^[0-7]{3,4}$`
- Accepts 3 or 4 digit octal strings (e.g., "644", "0755")

**File Size Checks:**

- Configured via `MAX_FILE_SIZE` environment variable (default: 10MB)
- Checked before download (container files)
- Checked before upload (local files)
- Prevents resource exhaustion and excessive token usage

**Overwrite Protection:**

- Default: `overwrite=False` prevents accidental file replacement
- Downloads: Check if local file exists before starting
- Uploads to containers: Use `pct exec <vmid> -- test -f <path>`
- Uploads to host: Use `test -f <path>`

### Configuration

**ProxmoxConfig class:**

```python
self.max_file_size = int(os.getenv("MAX_FILE_SIZE", "10485760"))  # 10MB
self.server_port = int(os.getenv("SERVER_PORT", "8000"))  # 8000
```

**Environment Variables:**

```bash
MAX_FILE_SIZE=10485760  # 10 MB (default)
SERVER_PORT=8000        # 8000 (default) - HTTP server port for Docker/HTTP mode
```

## Important Implementation Details

### Command Escaping

When executing commands inside containers, single quotes in the command must be escaped as `'\''` because the entire command is wrapped in single quotes for `bash -c`:

```python
escaped_command = command.replace("'", "'\\''")
pct_command = f"pct exec {vmid} -- bash -c '{escaped_command}'"
```

See the `proxmox_container_exec_command` function implementation.

### SSH Connection Lifecycle

The SSH connection is managed through FastMCP's `lifespan` context manager:

- Connection established at server startup in the `lifespan` function
- Connection closed at server shutdown
- Global `ssh_manager` variable provides access throughout tool functions

### Error Handling Pattern

Tools follow a consistent error handling pattern:

1. Check if `ssh_manager` is initialized
2. Execute SSH command with timeout
3. Check exit code (0 = success)
4. Parse output or return structured error
5. Return JSON or text based on `response_format`

Error responses include `suggestion` field to guide users (e.g., "Use 'proxmox_list_containers' to see available containers").

### Security Features

- **Risk Acceptance Gate**: Server refuses to start without `I_ACCEPT_RISKS=true`
- **Host Exec Disabled**: `proxmox_host_exec_command` disabled by default
- **Input Validation**: All inputs validated with Pydantic (ranges, length limits)
- **Command Timeout**: Maximum 300 seconds to prevent hanging
- **No Credential Storage**: All credentials from environment variables
- **SSH Key Support**: Prefer SSH keys over passwords

## Testing Approach

Since this is an MCP server, testing requires:

1. **Unit Testing** (if implementing):
   - Mock SSH connections using `unittest.mock`
   - Test parsing functions (`parse_pct_list_output`, `parse_pct_status_output`)
   - Validate input models with invalid data

2. **Integration Testing**:
   - Requires actual Proxmox environment
   - Test each tool with real containers
   - Verify error handling with invalid VMIDs
   - Test both password and SSH key authentication

3. **Manual Testing via Claude Desktop**:
   - Configure Claude Desktop with server
   - Send natural language requests to Claude
   - Verify tool selection and execution

## Common Development Scenarios

### Adding a New Tool

1. Create Pydantic input model in the Input Validation Models section
2. Add tool function with `@mcp.tool()` decorator
3. Include comprehensive docstring (used by AI to understand tool)
4. Set appropriate annotations (`readOnlyHint`, `destructiveHint`, etc.)
5. Follow error handling pattern from existing tools
6. Update README.md "Available Tools" section

### Modifying Command Execution

The core execution logic is in `SSHConnectionManager.execute_command()` method. Changes here affect all tools.

### Adjusting Output Format

Output formatting is handled by `format_exec_output()` function. This function supports both JSON and text formats.

### Handling Long Outputs

Increase `CHARACTER_LIMIT` environment variable or modify `truncate_output()` function. Consider implications for token usage in AI context.

## Security Considerations When Contributing

- Never bypass the `I_ACCEPT_RISKS` check
- Keep `ENABLE_HOST_EXEC` default as `false`
- Mark destructive tools with `destructiveHint: True`
- Validate all user inputs with Pydantic models
- Document security implications in tool docstrings
- Test with least-privilege users when possible
- Never log or expose credentials

## Why SSH Instead of Proxmox API?

The Proxmox API does **not** support executing arbitrary commands inside containers. The `pct exec` CLI command is the official method for container command execution, which requires SSH access to the Proxmox host.
