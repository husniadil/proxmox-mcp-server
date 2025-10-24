#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp>=1.0.0",
#     "fastmcp>=2.12.5",
#     "paramiko>=4.0.0",
#     "pydantic>=2.12.3",
#     "python-dotenv>=1.1.1",
#     "uvicorn>=0.38.0",
# ]
# ///
"""
Proxmox MCP Server - Execute commands in LXC containers via SSH

This MCP server enables LLMs to interact with Proxmox VE containers by:
- Executing bash commands inside containers using 'pct exec'
- Managing container lifecycle (start, stop, status)
- Listing available containers
- Transferring files to/from containers and host

The server connects to the Proxmox host via SSH and uses the 'pct' command-line tool.
"""

import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple

import paramiko
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict

# Load environment variables from .env file
load_dotenv()

# ============================================================================
# Constants
# ============================================================================

# Default character limit (can be overridden via environment variable)
DEFAULT_CHARACTER_LIMIT = 25000

# ============================================================================
# Configuration Models
# ============================================================================


class ProxmoxConfig:
    """Proxmox connection configuration from environment variables"""

    def __init__(self):
        self.host = os.getenv("HOST")
        self.port = int(os.getenv("SSH_PORT", "22"))
        self.username = os.getenv("SSH_USERNAME", "root")
        self.password = os.getenv("SSH_PASSWORD")
        self.key_path = os.getenv("SSH_KEY")
        # CRITICAL: User must explicitly accept risks
        self.accept_risks = os.getenv("I_ACCEPT_RISKS", "false").lower() == "true"
        # Feature flag for host command execution (default: disabled for safety)
        self.enable_host_exec = os.getenv("ENABLE_HOST_EXEC", "false").lower() == "true"
        # Maximum character limit for responses (default: 25000)
        self.character_limit = int(
            os.getenv("CHARACTER_LIMIT", str(DEFAULT_CHARACTER_LIMIT))
        )
        # Maximum file size for transfers in bytes (default: 10MB)
        self.max_file_size = int(os.getenv("MAX_FILE_SIZE", "10485760"))

    def validate(self) -> Tuple[bool, Optional[str]]:
        """Validate configuration"""
        # CRITICAL: Check risk acceptance FIRST
        if not self.accept_risks:
            return False, (
                "You must explicitly accept the risks before using this software.\n"
                "Set environment variable: I_ACCEPT_RISKS=true\n\n"
                "By setting this to 'true', you acknowledge that:\n"
                "  - You understand the risks of giving AI system SSH access to your infrastructure\n"
                "  - You are solely responsible for reviewing and approving commands\n"
                "  - You have proper backups and disaster recovery procedures in place\n"
                "  - You will not hold the developer(s) liable for any damages or losses\n\n"
                "See README DISCLAIMER section for full details."
            )

        if not self.host:
            return False, "HOST environment variable is required"

        if not self.password and not self.key_path:
            return False, "Either SSH_PASSWORD or SSH_KEY must be set"

        return True, None


# ============================================================================
# Input Models
# ============================================================================


class ResponseFormat(str, Enum):
    """Output format for tool responses"""

    JSON = "json"
    TEXT = "text"


class ExecCommandInput(BaseModel):
    """Input model for executing commands in a container"""

    model_config = ConfigDict(
        str_strip_whitespace=True, validate_assignment=True, extra="forbid"
    )

    vmid: int = Field(
        ..., description="Container VM ID (e.g., 100, 101, 102)", ge=100, le=999999999
    )
    command: str = Field(
        ...,
        description="Bash command to execute in the container (e.g., 'ls -la', 'df -h', 'apt update')",
        min_length=1,
        max_length=10000,
    )
    timeout: Optional[int] = Field(
        default=30, description="Command timeout in seconds (default: 30)", ge=1, le=300
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.TEXT,
        description="Output format: 'text' for raw output or 'json' for structured data",
    )


class ContainerStatusInput(BaseModel):
    """Input model for getting container status"""

    model_config = ConfigDict(
        str_strip_whitespace=True, validate_assignment=True, extra="forbid"
    )

    vmid: int = Field(
        ..., description="Container VM ID to check status for", ge=100, le=999999999
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.JSON,
        description="Output format: 'json' for structured data or 'text' for human-readable",
    )


class ContainerActionInput(BaseModel):
    """Input model for container actions (start/stop)"""

    model_config = ConfigDict(
        str_strip_whitespace=True, validate_assignment=True, extra="forbid"
    )

    vmid: int = Field(
        ..., description="Container VM ID to perform action on", ge=100, le=999999999
    )


class ListContainersInput(BaseModel):
    """Input model for listing containers"""

    model_config = ConfigDict(
        str_strip_whitespace=True, validate_assignment=True, extra="forbid"
    )

    response_format: ResponseFormat = Field(
        default=ResponseFormat.JSON,
        description="Output format: 'json' for structured data or 'text' for human-readable",
    )


class HostExecCommandInput(BaseModel):
    """Input model for executing commands on Proxmox host"""

    model_config = ConfigDict(
        str_strip_whitespace=True, validate_assignment=True, extra="forbid"
    )

    command: str = Field(
        ...,
        description="Bash command to execute on the Proxmox host (e.g., 'pct list', 'df -h', 'pvecm status')",
        min_length=1,
        max_length=10000,
    )
    timeout: Optional[int] = Field(
        default=30, description="Command timeout in seconds (default: 30)", ge=1, le=300
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.TEXT,
        description="Output format: 'text' for raw output or 'json' for structured data",
    )


class DownloadFileFromContainerInput(BaseModel):
    """Input model for downloading files from container"""

    model_config = ConfigDict(
        str_strip_whitespace=True, validate_assignment=True, extra="forbid"
    )

    vmid: int = Field(
        ..., description="Container VM ID to download file from", ge=100, le=999999999
    )
    container_path: str = Field(
        ...,
        description="Path to file inside the container (e.g., '/etc/nginx/nginx.conf')",
        min_length=1,
        max_length=4096,
    )
    local_path: str = Field(
        ...,
        description="Local path where file will be saved (e.g., './nginx.conf')",
        min_length=1,
        max_length=4096,
    )
    overwrite: bool = Field(
        default=False,
        description="Whether to overwrite local file if it exists (default: False)",
    )


class UploadFileToContainerInput(BaseModel):
    """Input model for uploading files to container"""

    model_config = ConfigDict(
        str_strip_whitespace=True, validate_assignment=True, extra="forbid"
    )

    vmid: int = Field(
        ..., description="Container VM ID to upload file to", ge=100, le=999999999
    )
    local_path: str = Field(
        ...,
        description="Local path to file to upload (e.g., './config.yaml')",
        min_length=1,
        max_length=4096,
    )
    container_path: str = Field(
        ...,
        description="Destination path inside container (e.g., '/etc/app/config.yaml')",
        min_length=1,
        max_length=4096,
    )
    permissions: str = Field(
        default="644",
        description="File permissions in octal format (e.g., '644', '755')",
    )
    overwrite: bool = Field(
        default=False,
        description="Whether to overwrite container file if it exists (default: False)",
    )


class DownloadFileFromHostInput(BaseModel):
    """Input model for downloading files from Proxmox host"""

    model_config = ConfigDict(
        str_strip_whitespace=True, validate_assignment=True, extra="forbid"
    )

    host_path: str = Field(
        ...,
        description="Path to file on Proxmox host (e.g., '/etc/pve/storage.cfg')",
        min_length=1,
        max_length=4096,
    )
    local_path: str = Field(
        ...,
        description="Local path where file will be saved (e.g., './storage.cfg')",
        min_length=1,
        max_length=4096,
    )
    overwrite: bool = Field(
        default=False,
        description="Whether to overwrite local file if it exists (default: False)",
    )


class UploadFileToHostInput(BaseModel):
    """Input model for uploading files to Proxmox host"""

    model_config = ConfigDict(
        str_strip_whitespace=True, validate_assignment=True, extra="forbid"
    )

    local_path: str = Field(
        ...,
        description="Local path to file to upload (e.g., './script.sh')",
        min_length=1,
        max_length=4096,
    )
    host_path: str = Field(
        ...,
        description="Destination path on Proxmox host (e.g., '/root/script.sh')",
        min_length=1,
        max_length=4096,
    )
    permissions: str = Field(
        default="644",
        description="File permissions in octal format (e.g., '644', '755')",
    )
    overwrite: bool = Field(
        default=False,
        description="Whether to overwrite host file if it exists (default: False)",
    )


# ============================================================================
# SSH Connection Manager
# ============================================================================


class SSHConnectionManager:
    """Manages SSH connections to Proxmox host"""

    def __init__(self, config: ProxmoxConfig):
        self.config = config
        self._client: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None

    def connect(self) -> None:
        """Establish SSH connection to Proxmox host"""
        if self._client is not None:
            return

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            if self.config.key_path:
                # Connect using SSH key
                self._client.connect(
                    hostname=self.config.host,
                    port=self.config.port,
                    username=self.config.username,
                    key_filename=self.config.key_path,
                    timeout=10,
                )
            else:
                # Connect using password
                self._client.connect(
                    hostname=self.config.host,
                    port=self.config.port,
                    username=self.config.username,
                    password=self.config.password,
                    timeout=10,
                )
        except Exception as e:
            self._client = None
            raise ConnectionError(
                f"Failed to connect to Proxmox host {self.config.host}: {str(e)}"
            )

    def disconnect(self) -> None:
        """Close SSH connection"""
        if self._sftp:
            self._sftp.close()
            self._sftp = None
        if self._client:
            self._client.close()
            self._client = None

    def get_sftp_client(self) -> paramiko.SFTPClient:
        """Get or create SFTP client

        Returns:
            SFTP client for file transfers
        """
        if not self._client:
            raise RuntimeError("SSH client not connected. Call connect() first.")

        if not self._sftp:
            self._sftp = self._client.open_sftp()

        return self._sftp

    async def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a file from remote host to local machine

        Args:
            remote_path: Path on remote host
            local_path: Path on local machine

        Raises:
            RuntimeError: If download fails
        """
        try:
            sftp = self.get_sftp_client()
            sftp.get(remote_path, local_path)
        except Exception as e:
            raise RuntimeError(f"Failed to download file from {remote_path}: {str(e)}")

    async def upload_file(self, local_path: str, remote_path: str) -> None:
        """Upload a file from local machine to remote host

        Args:
            local_path: Path on local machine
            remote_path: Path on remote host

        Raises:
            RuntimeError: If upload fails
        """
        try:
            sftp = self.get_sftp_client()
            sftp.put(local_path, remote_path)
        except Exception as e:
            raise RuntimeError(f"Failed to upload file to {remote_path}: {str(e)}")

    async def cleanup_remote_file(self, remote_path: str) -> None:
        """Remove a file from remote host

        Args:
            remote_path: Path on remote host to remove
        """
        try:
            sftp = self.get_sftp_client()
            sftp.remove(remote_path)
        except Exception:
            # Ignore errors during cleanup
            pass

    async def execute_command(
        self, command: str, timeout: int = 30
    ) -> Tuple[str, str, int]:
        """
        Execute a command via SSH

        Returns:
            Tuple: (stdout, stderr, exit_code)
        """
        if not self._client:
            raise RuntimeError("SSH client not connected. Call connect() first.")

        try:
            stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)

            # Wait for command to complete
            exit_code = stdout.channel.recv_exit_status()

            stdout_data = stdout.read().decode("utf-8", errors="replace")
            stderr_data = stderr.read().decode("utf-8", errors="replace")

            return stdout_data, stderr_data, exit_code

        except Exception as e:
            raise RuntimeError(f"Failed to execute command: {str(e)}")


# ============================================================================
# Helper Functions
# ============================================================================


def parse_pct_list_output(output: str) -> List[Dict[str, Any]]:
    """Parse 'pct list' command output into structured data"""
    lines = output.strip().split("\n")
    if len(lines) < 2:
        return []

    # First line is header
    containers = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 3:
            containers.append(
                {
                    "vmid": int(parts[0]),
                    "status": parts[1],
                    "name": parts[2] if len(parts) > 2 else "",
                }
            )

    return containers


def parse_pct_status_output(output: str) -> Dict[str, str]:
    """Parse 'pct status' command output"""
    output = output.strip().lower()
    if "running" in output:
        status = "running"
    elif "stopped" in output:
        status = "stopped"
    else:
        status = "unknown"

    return {"status": status}


def format_exec_output(
    stdout: str,
    stderr: str,
    exit_code: int,
    format_type: ResponseFormat,
    max_length: Optional[int] = None,
) -> str:
    """Format command execution output with proper truncation handling

    For JSON format: Truncates stdout/stderr BEFORE creating JSON to keep structure valid
    For text format: Formats then truncates the entire output

    Args:
        stdout: Command stdout
        stderr: Command stderr
        exit_code: Command exit code
        format_type: Output format (JSON or TEXT)
        max_length: Maximum output length (uses global character_limit if not specified)

    Returns:
        Formatted output string (guaranteed valid JSON if format_type is JSON)
    """
    if max_length is None:
        max_length = character_limit

    if format_type == ResponseFormat.JSON:
        # For JSON: truncate data BEFORE creating JSON object to keep it valid
        # Reserve space for JSON structure overhead (~500 chars for metadata)
        json_overhead = 500
        available_space = max(
            max_length - json_overhead, 1000
        )  # Minimum 1000 chars for data

        # Calculate original lengths
        stdout_original_len = len(stdout)
        stderr_original_len = len(stderr)
        total_len = stdout_original_len + stderr_original_len

        # Track if truncation occurred
        stdout_truncated = False
        stderr_truncated = False

        if total_len > available_space:
            # Need to truncate - allocate space proportionally
            if total_len > 0:
                stdout_ratio = stdout_original_len / total_len
                stderr_ratio = stderr_original_len / total_len

                stdout_limit = int(available_space * stdout_ratio)
                stderr_limit = int(available_space * stderr_ratio)
            else:
                stdout_limit = available_space // 2
                stderr_limit = available_space // 2

            if stdout_original_len > stdout_limit:
                stdout = stdout[:stdout_limit]
                stdout_truncated = True

            if stderr_original_len > stderr_limit:
                stderr = stderr[:stderr_limit]
                stderr_truncated = True

        # Build JSON object with truncation metadata
        result = {
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "success": exit_code == 0,
        }

        # Add truncation metadata if needed
        if stdout_truncated:
            result["stdout_truncated"] = True
            result["stdout_original_length"] = stdout_original_len

        if stderr_truncated:
            result["stderr_truncated"] = True
            result["stderr_original_length"] = stderr_original_len

        return json.dumps(result, indent=2)
    else:
        # Text format: format then truncate
        output_parts = []
        if stdout:
            output_parts.append(f"=== STDOUT ===\n{stdout}")
        if stderr:
            output_parts.append(f"=== STDERR ===\n{stderr}")
        output_parts.append(f"=== EXIT CODE: {exit_code} ===")

        output = "\n\n".join(output_parts)

        # Truncate if needed
        if len(output) > max_length:
            truncated = output[:max_length]
            truncation_msg = f"\n\n[OUTPUT TRUNCATED - showing first {max_length} of {len(output)} characters]"
            return truncated + truncation_msg

        return output


def truncate_output(output: str, max_length: Optional[int] = None) -> str:
    """Truncate output if it exceeds max length"""
    if max_length is None:
        max_length = character_limit

    if len(output) <= max_length:
        return output

    truncated = output[:max_length]
    truncation_msg = f"\n\n[OUTPUT TRUNCATED - showing first {max_length} of {len(output)} characters]"
    return truncated + truncation_msg


def validate_path(path: str) -> Tuple[bool, Optional[str]]:
    """Validate file path to prevent security issues

    Args:
        path: Path to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not path or not path.strip():
        return False, "Path cannot be empty"

    # Check for path traversal attempts
    if ".." in path:
        return False, "Path cannot contain '..' (path traversal not allowed)"

    # Path should not be too long
    if len(path) > 4096:
        return False, "Path exceeds maximum length of 4096 characters"

    return True, None


def get_temp_path() -> str:
    """Generate unique temporary file path on Proxmox host

    Returns:
        Unique temporary path like /tmp/proxmox-mcp-{uuid}
    """
    return f"/tmp/proxmox-mcp-{uuid.uuid4().hex}"


def validate_permissions(perms: str) -> Tuple[bool, Optional[str]]:
    """Validate permission string is valid octal

    Args:
        perms: Permission string (e.g., "644", "755")

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not perms:
        return False, "Permissions cannot be empty"

    # Check if it's a valid octal string (3 or 4 digits, all 0-7)
    if not re.match(r"^[0-7]{3,4}$", perms):
        return (
            False,
            "Permissions must be a valid octal string (e.g., '644', '755', '0644')",
        )

    return True, None


# ============================================================================
# Initialize FastMCP Server
# ============================================================================

# Global SSH connection manager and configuration
ssh_manager: Optional[SSHConnectionManager] = None
character_limit: int = DEFAULT_CHARACTER_LIMIT
mcp_app = None  # ASGI app for HTTP mode (set during startup)


@asynccontextmanager
async def lifespan(app):
    """Manage SSH connection lifecycle"""
    global ssh_manager, character_limit

    # Initialize configuration
    config = ProxmoxConfig()
    is_valid, error_msg = config.validate()

    if not is_valid:
        print(f"Configuration error: {error_msg}")
        print("\nRequired environment variables:")
        print(
            "  I_ACCEPT_RISKS - MUST be set to 'true' to acknowledge risks (REQUIRED)"
        )
        print("  HOST - Proxmox host IP or hostname")
        print("  SSH_USERNAME - SSH username (default: root)")
        print("  SSH_PORT - SSH port (default: 22)")
        print("  SSH_PASSWORD - SSH password (or use SSH_KEY)")
        print("  SSH_KEY - Path to SSH private key (or use SSH_PASSWORD)")
        raise RuntimeError(error_msg)

    # Set global character limit from config
    character_limit = config.character_limit

    # Create SSH manager
    ssh_manager = SSHConnectionManager(config)

    try:
        # Connect to Proxmox host
        ssh_manager.connect()
        print(f"Connected to Proxmox host: {config.host}")

        yield {"ssh_manager": ssh_manager}

    finally:
        # Cleanup
        if ssh_manager:
            ssh_manager.disconnect()
            print("Disconnected from Proxmox host")


mcp = FastMCP("proxmox_mcp", lifespan=lifespan)

# ============================================================================
# Tools
# ============================================================================


@mcp.tool(
    name="proxmox_container_exec_command",
    annotations={
        "title": "Execute Bash Command in Proxmox Container",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def proxmox_container_exec_command(
    vmid: int, command: str, timeout: int = 30, response_format: str = "text"
) -> str:
    """Execute a bash command inside a Proxmox LXC container.

    This tool runs commands inside containers using SSH and 'pct exec'.
    It provides full access to the container's shell environment.

    Use cases:
    - System administration tasks (checking disk space, memory usage)
    - Software installation and updates
    - File operations (creating, reading, modifying files)
    - Service management (starting/stopping services)
    - Log inspection and debugging

    Args:
        vmid (int): Container VM ID (100-999999999)
        command (str): Bash command to execute
        timeout (int, optional): Command timeout in seconds (default: 30, max: 300)
        response_format (str): Output format - 'text' or 'json' (default: 'text')

    Returns:
        str: Command output in the requested format:
            - JSON format: {"exit_code": int, "stdout": str, "stderr": str, "success": bool}
            - TEXT format: Raw stdout/stderr with exit code

    Example:
        {"vmid": 100, "command": "df -h", "response_format": "text"}
        {"vmid": 101, "command": "apt update && apt upgrade -y", "timeout": 120}

    IMPORTANT - Interactive Commands (REPLs):
        This tool does NOT support interactive commands like python, node, mysql, redis-cli, etc.
        Interactive commands will hang until timeout.

        Instead, use these patterns:
        - Python: Use `python -c "print('hello')"` or heredoc for multi-line:
          python << 'EOF'
          import sys
          print(sys.version)
          print('Hello from Python')
          EOF

        - Node.js: Use `node -e "console.log('hello')"` or heredoc:
          node << 'EOF'
          console.log(process.version);
          console.log('Hello from Node');
          EOF

        - MySQL: Use `mysql -e "SELECT * FROM table"` or heredoc:
          mysql -u root -p'password' << 'EOF'
          USE mydb;
          SELECT * FROM users LIMIT 10;
          EOF

        - Redis: Use `redis-cli --eval script.lua` or `redis-cli GET key`

    Error handling:
        - If container doesn't exist: Returns error message with available containers
        - If command fails: Returns stderr and non-zero exit code
        - If timeout: Returns timeout error after specified seconds
        - If SSH connection fails: Returns connection error with troubleshooting steps
    """
    global ssh_manager

    if not ssh_manager:
        return json.dumps({"error": "SSH connection not initialized", "success": False})

    try:
        # Convert response_format string to ResponseFormat enum
        fmt = ResponseFormat(response_format.lower())

        # Build pct exec command
        # Escape single quotes in the command
        escaped_command = command.replace("'", "'\\''")
        pct_command = f"pct exec {vmid} -- bash -c '{escaped_command}'"

        # Execute command
        stdout, stderr, exit_code = await ssh_manager.execute_command(
            pct_command, timeout=timeout
        )

        # Format output (truncation handled internally)
        return format_exec_output(stdout, stderr, exit_code, fmt)

    except Exception as e:
        error_msg = str(e)

        if response_format.lower() == "json":
            return json.dumps(
                {
                    "error": error_msg,
                    "success": False,
                    "suggestion": "Check if container exists and is running using 'proxmox_list_containers' tool",
                },
                indent=2,
            )
        else:
            return f"Error: {error_msg}\n\nSuggestion: Check if container exists and is running using 'proxmox_list_containers' tool"


@mcp.tool(
    name="proxmox_list_containers",
    annotations={
        "title": "List All Proxmox Containers",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def proxmox_list_containers(response_format: str = "json") -> str:
    """List all LXC containers on the Proxmox host.

    This tool retrieves information about all containers including their
    VM ID, status (running/stopped), and name.

    Args:
        response_format (str): Output format - 'json' or 'text' (default: 'json')

    Returns:
        str: List of containers in requested format:
            - JSON format: [{"vmid": int, "status": str, "name": str}, ...]
            - TEXT format: Human-readable table of containers

    Example:
        {"response_format": "json"}
        {"response_format": "text"}
    """
    global ssh_manager

    if not ssh_manager:
        return json.dumps({"error": "SSH connection not initialized", "success": False})

    try:
        # Execute pct list
        stdout, stderr, exit_code = await ssh_manager.execute_command("pct list")

        if exit_code != 0:
            return json.dumps(
                {
                    "error": "Failed to list containers",
                    "stderr": stderr,
                    "success": False,
                },
                indent=2,
            )

        # Parse output
        containers = parse_pct_list_output(stdout)

        if response_format.lower() == "json":
            return json.dumps(containers, indent=2)
        else:
            # Text format
            if not containers:
                return "No containers found"

            lines = ["VMID | Status | Name", "-" * 40]
            for ct in containers:
                lines.append(f"{ct['vmid']:4d} | {ct['status']:7s} | {ct['name']}")

            return "\n".join(lines)

    except Exception as e:
        return json.dumps({"error": str(e), "success": False}, indent=2)


@mcp.tool(
    name="proxmox_container_status",
    annotations={
        "title": "Get Proxmox Container Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def proxmox_container_status(vmid: int, response_format: str = "json") -> str:
    """Get the current status of a specific Proxmox LXC container.

    This tool checks whether a container is running, stopped, or in another state.

    Args:
        vmid (int): Container VM ID to check
        response_format (str): Output format - 'json' or 'text' (default: 'json')

    Returns:
        str: Container status in requested format:
            - JSON format: {"status": "running"|"stopped"|"unknown"}
            - TEXT format: Human-readable status message

    Example:
        {"vmid": 100}
        {"vmid": 101, "response_format": "text"}
    """
    global ssh_manager

    if not ssh_manager:
        return json.dumps({"error": "SSH connection not initialized", "success": False})

    try:
        # Execute pct status
        stdout, stderr, exit_code = await ssh_manager.execute_command(
            f"pct status {vmid}"
        )

        if exit_code != 0:
            return json.dumps(
                {
                    "error": f"Container {vmid} not found or error occurred",
                    "stderr": stderr,
                    "success": False,
                    "suggestion": "Use 'proxmox_list_containers' to see available containers",
                },
                indent=2,
            )

        # Parse status
        status_data = parse_pct_status_output(stdout)

        if response_format.lower() == "json":
            return json.dumps(status_data, indent=2)
        else:
            return f"Container {vmid} is {status_data['status']}"

    except Exception as e:
        return json.dumps({"error": str(e), "success": False}, indent=2)


@mcp.tool(
    name="proxmox_start_container",
    annotations={
        "title": "Start Proxmox Container",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def proxmox_start_container(vmid: int) -> str:
    """Start a stopped Proxmox LXC container.

    This tool starts a container if it's currently stopped. If the container
    is already running, the operation has no effect (idempotent).

    Args:
        vmid (int): Container VM ID to start

    Returns:
        str: JSON result with success status and message

    Example:
        {"vmid": 100}
    """
    global ssh_manager

    if not ssh_manager:
        return json.dumps({"error": "SSH connection not initialized", "success": False})

    try:
        # Execute pct start
        stdout, stderr, exit_code = await ssh_manager.execute_command(
            f"pct start {vmid}"
        )

        if exit_code != 0:
            return json.dumps(
                {
                    "error": f"Failed to start container {vmid}",
                    "stderr": stderr,
                    "success": False,
                    "suggestion": "Check if container exists using 'proxmox_list_containers'",
                },
                indent=2,
            )

        return json.dumps(
            {
                "success": True,
                "message": f"Container {vmid} started successfully",
                "vmid": vmid,
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps({"error": str(e), "success": False}, indent=2)


@mcp.tool(
    name="proxmox_stop_container",
    annotations={
        "title": "Stop Proxmox Container",
        "readOnlyHint": False,
        "destructiveHint": True,  # Stops services and causes downtime
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def proxmox_stop_container(vmid: int) -> str:
    """Stop a running Proxmox LXC container.

    This tool gracefully stops a container if it's currently running. If the
    container is already stopped, the operation has no effect (idempotent).

    Args:
        vmid (int): Container VM ID to stop

    Returns:
        str: JSON result with success status and message

    Example:
        {"vmid": 100}
    """
    global ssh_manager

    if not ssh_manager:
        return json.dumps({"error": "SSH connection not initialized", "success": False})

    try:
        # Execute pct stop
        stdout, stderr, exit_code = await ssh_manager.execute_command(
            f"pct stop {vmid}"
        )

        if exit_code != 0:
            return json.dumps(
                {
                    "error": f"Failed to stop container {vmid}",
                    "stderr": stderr,
                    "success": False,
                    "suggestion": "Check if container exists and is running using 'proxmox_container_status'",
                },
                indent=2,
            )

        return json.dumps(
            {
                "success": True,
                "message": f"Container {vmid} stopped successfully",
                "vmid": vmid,
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps({"error": str(e), "success": False}, indent=2)


@mcp.tool(
    name="proxmox_host_exec_command",
    annotations={
        "title": "Execute Bash Command on Proxmox Host",
        "readOnlyHint": False,
        "destructiveHint": True,  # CRITICAL: This can affect entire infrastructure
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def proxmox_host_exec_command(
    command: str, timeout: int = 30, response_format: str = "text"
) -> str:
    """Execute a bash command directly on the Proxmox host.

    ⚠️ CRITICAL WARNING: This executes commands directly on your Proxmox host
    with root privileges. This can affect ALL containers/VMs and the host itself.
    Use with EXTREME caution!

    Unlike 'proxmox_container_exec_command' which runs inside a specific container, this
    tool runs commands directly on the Proxmox host system. This gives you full
    access to the hypervisor and all its resources.

    Common use cases:
    - **Node Operations**: Check host resources (df -h, free -h, uptime)
    - **Container/VM Management**: List all containers/VMs (pct list, qm list)
    - **Cluster Status**: Check cluster health (pvecm status)
    - **Storage Management**: ZFS operations (zpool status, zfs list)
    - **System Administration**: Service management, network diagnostics
    - **Proxmox Operations**: Backup status, storage status (pvesm status)

    Safety Levels:

    ✅ SAFE (Read-Only):
        - pct list, qm list          (List containers/VMs)
        - pvecm status               (Cluster status)
        - df -h, free -h             (Resource checks)
        - zpool status, zfs list     (Storage info)
        - pvesm status               (Storage status)
        - uptime, who                (System info)

    ⚠️ MODERATE RISK:
        - pct create                 (Create container)
        - pct start/stop             (Manage containers)
        - systemctl restart pveproxy (Restart services)
        - apt update                 (Update package lists)

    🔴 HIGH RISK:
        - pct destroy                (Delete container)
        - apt upgrade -y             (Upgrade packages)
        - systemctl stop pveproxy    (Stop Proxmox service)
        - shutdown, reboot           (Shutdown/reboot host)

    ⛔ DANGEROUS - AVOID:
        - rm -rf                     (Delete files)
        - dd, mkfs                   (Disk operations)
        - Commands affecting /dev    (Device operations)

    Args:
        command (str): Bash command to execute on the host
        timeout (int, optional): Command timeout in seconds (default: 30, max: 300)
        response_format (str): Output format - 'text' or 'json' (default: 'text')

    Returns:
        str: Command output in the requested format:
            - JSON format: {"exit_code": int, "stdout": str, "stderr": str, "success": bool}
            - TEXT format: Raw stdout/stderr with exit code

    Examples:
        {"command": "pct list", "response_format": "text"}
        {"command": "pvecm status"}
        {"command": "df -h && free -h", "timeout": 60}
        {"command": "zpool status"}

    IMPORTANT - Interactive Commands (REPLs):
        This tool does NOT support interactive commands like python, node, mysql, redis-cli, etc.
        Interactive commands will hang until timeout.

        Instead, use these patterns:
        - Python: Use `python -c "print('hello')"` or heredoc for multi-line:
          python << 'EOF'
          import sys
          print(sys.version)
          print('Hello from Python')
          EOF

        - Node.js: Use `node -e "console.log('hello')"` or heredoc:
          node << 'EOF'
          console.log(process.version);
          console.log('Hello from Node');
          EOF

        - MySQL: Use `mysql -e "SELECT * FROM table"` or heredoc:
          mysql -u root -p'password' << 'EOF'
          USE mydb;
          SELECT * FROM users LIMIT 10;
          EOF

        - Redis: Use `redis-cli --eval script.lua` or `redis-cli GET key`

    Error handling:
        - If host exec is disabled: Returns error asking to enable ENABLE_HOST_EXEC
        - If command fails: Returns stderr and non-zero exit code
        - If timeout: Returns timeout error after specified seconds
        - If SSH connection fails: Returns connection error

    Security:
        - This feature is DISABLED by default
        - Enable by setting: ENABLE_HOST_EXEC=true
        - All commands execute with the privileges of the SSH user (typically root)
        - No command filtering - relies on user responsibility
        - Use read-only commands when possible
    """
    global ssh_manager

    if not ssh_manager:
        return json.dumps({"error": "SSH connection not initialized", "success": False})

    # Safety check: Feature must be explicitly enabled
    if not ssh_manager.config.enable_host_exec:
        return json.dumps(
            {
                "error": "Host command execution is DISABLED for safety",
                "success": False,
                "message": "To enable this feature, set environment variable: ENABLE_HOST_EXEC=true",
                "reason": "This feature can affect your entire Proxmox infrastructure and is disabled by default",
                "documentation": "See README for security considerations and best practices",
            },
            indent=2,
        )

    try:
        # Convert response_format string to ResponseFormat enum
        fmt = ResponseFormat(response_format.lower())

        # Execute command directly on host (NO pct exec wrapper)
        stdout, stderr, exit_code = await ssh_manager.execute_command(
            command, timeout=timeout
        )

        # Format output (truncation handled internally)
        return format_exec_output(stdout, stderr, exit_code, fmt)

    except Exception as e:
        error_msg = str(e)

        if response_format.lower() == "json":
            return json.dumps(
                {
                    "error": error_msg,
                    "success": False,
                    "suggestion": "Check if the command is valid and you have necessary permissions",
                },
                indent=2,
            )
        else:
            return f"Error: {error_msg}\n\nSuggestion: Check if the command is valid and you have necessary permissions"


@mcp.tool(
    name="proxmox_download_file_from_container",
    annotations={
        "title": "Download File from Proxmox Container",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def proxmox_download_file_from_container(
    vmid: int, container_path: str, local_path: str, overwrite: bool = False
) -> str:
    """Download a file from a Proxmox LXC container to local machine.

    This tool downloads files from inside containers to your local machine using:
    1. `pct pull` to transfer file from container to Proxmox host temp location
    2. SFTP to download from host to local machine
    3. Cleanup of temp files on host

    Use cases:
    - Download configuration files for backup or editing
    - Retrieve log files for analysis
    - Export data from containers
    - Backup important files before making changes

    Args:
        vmid (int): Container VM ID (100-999999999)
        container_path (str): Path to file inside container (e.g., '/etc/nginx/nginx.conf')
        local_path (str): Local path where file will be saved (e.g., './nginx.conf')
        overwrite (bool, optional): Whether to overwrite local file if exists (default: False)

    Returns:
        str: JSON result with success status and details

    Example:
        {"vmid": 100, "container_path": "/etc/nginx/nginx.conf", "local_path": "./nginx.conf"}
        {"vmid": 101, "container_path": "/var/log/app.log", "local_path": "./app.log", "overwrite": true}

    Error handling:
        - Container not found or not running
        - File not found in container
        - File too large (exceeds MAX_FILE_SIZE)
        - Permission denied
        - Local file exists and overwrite=false
        - Disk space issues
    """
    global ssh_manager

    if not ssh_manager:
        return json.dumps({"error": "SSH connection not initialized", "success": False})

    try:
        # Validate paths
        is_valid, error_msg = validate_path(container_path)
        if not is_valid:
            return json.dumps(
                {"error": f"Invalid container path: {error_msg}", "success": False},
                indent=2,
            )

        is_valid, error_msg = validate_path(local_path)
        if not is_valid:
            return json.dumps(
                {"error": f"Invalid local path: {error_msg}", "success": False},
                indent=2,
            )

        # Check if local file exists
        if os.path.exists(local_path) and not overwrite:
            return json.dumps(
                {
                    "error": f"Local file already exists: {local_path}",
                    "success": False,
                    "suggestion": "Set overwrite=true to replace existing file or choose a different path",
                },
                indent=2,
            )

        # Generate temp path on host
        temp_path = get_temp_path()

        try:
            # Pull file from container to host temp location
            pull_command = f"pct pull {vmid} {container_path} {temp_path}"
            stdout, stderr, exit_code = await ssh_manager.execute_command(pull_command)

            if exit_code != 0:
                return json.dumps(
                    {
                        "error": f"Failed to pull file from container {vmid}",
                        "stderr": stderr,
                        "success": False,
                        "suggestion": "Check if container exists, is running, and file path is correct",
                    },
                    indent=2,
                )

            # Check file size on host
            size_command = f"stat -c%s {temp_path}"
            stdout, stderr, exit_code = await ssh_manager.execute_command(size_command)

            if exit_code == 0:
                file_size = int(stdout.strip())
                if file_size > ssh_manager.config.max_file_size:
                    # Cleanup temp file
                    await ssh_manager.cleanup_remote_file(temp_path)
                    return json.dumps(
                        {
                            "error": f"File size ({file_size} bytes) exceeds maximum allowed ({ssh_manager.config.max_file_size} bytes)",
                            "success": False,
                            "suggestion": "Increase MAX_FILE_SIZE environment variable or choose a smaller file",
                        },
                        indent=2,
                    )

            # Download from host to local
            await ssh_manager.download_file(temp_path, local_path)

            # Cleanup temp file
            await ssh_manager.cleanup_remote_file(temp_path)

            # Get final file size
            local_file_size = os.path.getsize(local_path)

            return json.dumps(
                {
                    "success": True,
                    "message": f"File downloaded successfully from container {vmid}",
                    "vmid": vmid,
                    "container_path": container_path,
                    "local_path": local_path,
                    "bytes_transferred": local_file_size,
                },
                indent=2,
            )

        except Exception as e:
            # Cleanup temp file on error
            await ssh_manager.cleanup_remote_file(temp_path)
            raise e

    except Exception as e:
        return json.dumps({"error": str(e), "success": False}, indent=2)


@mcp.tool(
    name="proxmox_upload_file_to_container",
    annotations={
        "title": "Upload File to Proxmox Container",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def proxmox_upload_file_to_container(
    vmid: int,
    local_path: str,
    container_path: str,
    permissions: str = "644",
    overwrite: bool = False,
) -> str:
    """Upload a file from local machine to a Proxmox LXC container.

    This tool uploads files from your local machine to inside containers using:
    1. SFTP to upload from local to Proxmox host temp location
    2. `pct push` to transfer file from host to inside container
    3. Set file permissions inside container
    4. Cleanup of temp files on host

    Use cases:
    - Deploy configuration files to containers
    - Upload scripts for execution
    - Transfer data files to container applications
    - Update application code or assets

    Args:
        vmid (int): Container VM ID (100-999999999)
        local_path (str): Local path to file to upload (e.g., './config.yaml')
        container_path (str): Destination path inside container (e.g., '/etc/app/config.yaml')
        permissions (str, optional): File permissions in octal (default: "644")
        overwrite (bool, optional): Whether to overwrite container file if exists (default: False)

    Returns:
        str: JSON result with success status and details

    Example:
        {"vmid": 100, "local_path": "./nginx.conf", "container_path": "/etc/nginx/nginx.conf"}
        {"vmid": 101, "local_path": "./script.sh", "container_path": "/root/script.sh", "permissions": "755"}
        {"vmid": 102, "local_path": "./app.jar", "container_path": "/opt/app/app.jar", "overwrite": true}

    Error handling:
        - Local file not found
        - File too large (exceeds MAX_FILE_SIZE)
        - Container not found or not running
        - Permission denied
        - Container file exists and overwrite=false
        - Invalid permissions format
        - Disk space issues on host or container
    """
    global ssh_manager

    if not ssh_manager:
        return json.dumps({"error": "SSH connection not initialized", "success": False})

    try:
        # Validate permissions
        is_valid, error_msg = validate_permissions(permissions)
        if not is_valid:
            return json.dumps(
                {"error": f"Invalid permissions: {error_msg}", "success": False},
                indent=2,
            )

        # Validate paths
        is_valid, error_msg = validate_path(container_path)
        if not is_valid:
            return json.dumps(
                {"error": f"Invalid container path: {error_msg}", "success": False},
                indent=2,
            )

        is_valid, error_msg = validate_path(local_path)
        if not is_valid:
            return json.dumps(
                {"error": f"Invalid local path: {error_msg}", "success": False},
                indent=2,
            )

        # Check if local file exists
        if not os.path.exists(local_path):
            return json.dumps(
                {
                    "error": f"Local file not found: {local_path}",
                    "success": False,
                    "suggestion": "Check the local file path is correct and file exists",
                },
                indent=2,
            )

        # Check file size
        local_file_size = os.path.getsize(local_path)
        if local_file_size > ssh_manager.config.max_file_size:
            return json.dumps(
                {
                    "error": f"File size ({local_file_size} bytes) exceeds maximum allowed ({ssh_manager.config.max_file_size} bytes)",
                    "success": False,
                    "suggestion": "Increase MAX_FILE_SIZE environment variable or choose a smaller file",
                },
                indent=2,
            )

        # Check if container file exists (unless overwrite is true)
        if not overwrite:
            check_command = f"pct exec {vmid} -- test -f {container_path}"
            stdout, stderr, exit_code = await ssh_manager.execute_command(check_command)
            if exit_code == 0:
                return json.dumps(
                    {
                        "error": f"File already exists in container: {container_path}",
                        "success": False,
                        "suggestion": "Set overwrite=true to replace existing file or choose a different path",
                    },
                    indent=2,
                )

        # Generate temp path on host
        temp_path = get_temp_path()

        try:
            # Upload from local to host temp location
            await ssh_manager.upload_file(local_path, temp_path)

            # Push file from host to container
            push_command = f"pct push {vmid} {temp_path} {container_path}"
            stdout, stderr, exit_code = await ssh_manager.execute_command(push_command)

            if exit_code != 0:
                # Cleanup temp file
                await ssh_manager.cleanup_remote_file(temp_path)
                return json.dumps(
                    {
                        "error": f"Failed to push file to container {vmid}",
                        "stderr": stderr,
                        "success": False,
                        "suggestion": "Check if container exists, is running, and destination path is valid",
                    },
                    indent=2,
                )

            # Set permissions on the file inside container
            chmod_command = f"pct exec {vmid} -- chmod {permissions} {container_path}"
            stdout, stderr, exit_code = await ssh_manager.execute_command(chmod_command)

            if exit_code != 0:
                # File was uploaded but permissions failed - not critical
                pass

            # Cleanup temp file
            await ssh_manager.cleanup_remote_file(temp_path)

            return json.dumps(
                {
                    "success": True,
                    "message": f"File uploaded successfully to container {vmid}",
                    "vmid": vmid,
                    "local_path": local_path,
                    "container_path": container_path,
                    "permissions": permissions,
                    "bytes_transferred": local_file_size,
                },
                indent=2,
            )

        except Exception as e:
            # Cleanup temp file on error
            await ssh_manager.cleanup_remote_file(temp_path)
            raise e

    except Exception as e:
        return json.dumps({"error": str(e), "success": False}, indent=2)


@mcp.tool(
    name="proxmox_download_file_from_host",
    annotations={
        "title": "Download File from Proxmox Host",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def proxmox_download_file_from_host(
    host_path: str, local_path: str, overwrite: bool = False
) -> str:
    """Download a file from Proxmox host to local machine.

    ⚠️ This tool requires ENABLE_HOST_EXEC=true in your configuration.

    This tool downloads files directly from the Proxmox host using SFTP.
    Unlike container downloads, this accesses the host system directly.

    Use cases:
    - Download Proxmox configuration files
    - Backup host-level settings
    - Retrieve system logs from host
    - Export cluster configurations
    - Download scripts from host

    Args:
        host_path (str): Path to file on Proxmox host (e.g., '/etc/pve/storage.cfg')
        local_path (str): Local path where file will be saved (e.g., './storage.cfg')
        overwrite (bool, optional): Whether to overwrite local file if exists (default: False)

    Returns:
        str: JSON result with success status and details

    Example:
        {"host_path": "/etc/pve/storage.cfg", "local_path": "./storage.cfg"}
        {"host_path": "/var/log/syslog", "local_path": "./host-syslog.log", "overwrite": true}

    Error handling:
        - Feature disabled (ENABLE_HOST_EXEC=false)
        - File not found on host
        - File too large (exceeds MAX_FILE_SIZE)
        - Permission denied
        - Local file exists and overwrite=false
    """
    global ssh_manager

    if not ssh_manager:
        return json.dumps({"error": "SSH connection not initialized", "success": False})

    # Check if host exec is enabled
    if not ssh_manager.config.enable_host_exec:
        return json.dumps(
            {
                "error": "Host file operations are DISABLED for safety",
                "success": False,
                "message": "To enable this feature, set environment variable: ENABLE_HOST_EXEC=true",
                "reason": "Host operations can affect your entire Proxmox infrastructure",
                "documentation": "See README for security considerations and best practices",
            },
            indent=2,
        )

    try:
        # Validate paths
        is_valid, error_msg = validate_path(host_path)
        if not is_valid:
            return json.dumps(
                {"error": f"Invalid host path: {error_msg}", "success": False}, indent=2
            )

        is_valid, error_msg = validate_path(local_path)
        if not is_valid:
            return json.dumps(
                {"error": f"Invalid local path: {error_msg}", "success": False},
                indent=2,
            )

        # Check if local file exists
        if os.path.exists(local_path) and not overwrite:
            return json.dumps(
                {
                    "error": f"Local file already exists: {local_path}",
                    "success": False,
                    "suggestion": "Set overwrite=true to replace existing file or choose a different path",
                },
                indent=2,
            )

        # Check file size on host
        size_command = f"stat -c%s {host_path}"
        stdout, stderr, exit_code = await ssh_manager.execute_command(size_command)

        if exit_code != 0:
            return json.dumps(
                {
                    "error": f"File not found on host: {host_path}",
                    "stderr": stderr,
                    "success": False,
                    "suggestion": "Check if the host path is correct and file exists",
                },
                indent=2,
            )

        file_size = int(stdout.strip())
        if file_size > ssh_manager.config.max_file_size:
            return json.dumps(
                {
                    "error": f"File size ({file_size} bytes) exceeds maximum allowed ({ssh_manager.config.max_file_size} bytes)",
                    "success": False,
                    "suggestion": "Increase MAX_FILE_SIZE environment variable or choose a smaller file",
                },
                indent=2,
            )

        # Download directly from host
        await ssh_manager.download_file(host_path, local_path)

        # Get final file size
        local_file_size = os.path.getsize(local_path)

        return json.dumps(
            {
                "success": True,
                "message": f"File downloaded successfully from Proxmox host",
                "host_path": host_path,
                "local_path": local_path,
                "bytes_transferred": local_file_size,
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps({"error": str(e), "success": False}, indent=2)


@mcp.tool(
    name="proxmox_upload_file_to_host",
    annotations={
        "title": "Upload File to Proxmox Host",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def proxmox_upload_file_to_host(
    local_path: str, host_path: str, permissions: str = "644", overwrite: bool = False
) -> str:
    """Upload a file from local machine to Proxmox host.

    ⚠️ This tool requires ENABLE_HOST_EXEC=true in your configuration.

    This tool uploads files directly to the Proxmox host using SFTP.
    Unlike container uploads, this writes directly to the host system.

    **CRITICAL WARNING**: This modifies the Proxmox host system. Be extremely
    careful when uploading files to system directories.

    Use cases:
    - Deploy scripts to Proxmox host
    - Update host configurations
    - Upload backup files to host
    - Deploy automation scripts
    - Transfer files for later distribution to containers

    Args:
        local_path (str): Local path to file to upload (e.g., './script.sh')
        host_path (str): Destination path on Proxmox host (e.g., '/root/script.sh')
        permissions (str, optional): File permissions in octal (default: "644")
        overwrite (bool, optional): Whether to overwrite host file if exists (default: False)

    Returns:
        str: JSON result with success status and details

    Example:
        {"local_path": "./backup.sh", "host_path": "/root/backup.sh", "permissions": "755"}
        {"local_path": "./config.yaml", "host_path": "/etc/myapp/config.yaml", "overwrite": true}

    Error handling:
        - Feature disabled (ENABLE_HOST_EXEC=false)
        - Local file not found
        - File too large (exceeds MAX_FILE_SIZE)
        - Permission denied on host
        - Host file exists and overwrite=false
        - Invalid permissions format
        - Disk space issues on host
    """
    global ssh_manager

    if not ssh_manager:
        return json.dumps({"error": "SSH connection not initialized", "success": False})

    # Check if host exec is enabled
    if not ssh_manager.config.enable_host_exec:
        return json.dumps(
            {
                "error": "Host file operations are DISABLED for safety",
                "success": False,
                "message": "To enable this feature, set environment variable: ENABLE_HOST_EXEC=true",
                "reason": "Host operations can affect your entire Proxmox infrastructure",
                "documentation": "See README for security considerations and best practices",
            },
            indent=2,
        )

    try:
        # Validate permissions
        is_valid, error_msg = validate_permissions(permissions)
        if not is_valid:
            return json.dumps(
                {"error": f"Invalid permissions: {error_msg}", "success": False},
                indent=2,
            )

        # Validate paths
        is_valid, error_msg = validate_path(host_path)
        if not is_valid:
            return json.dumps(
                {"error": f"Invalid host path: {error_msg}", "success": False}, indent=2
            )

        is_valid, error_msg = validate_path(local_path)
        if not is_valid:
            return json.dumps(
                {"error": f"Invalid local path: {error_msg}", "success": False},
                indent=2,
            )

        # Check if local file exists
        if not os.path.exists(local_path):
            return json.dumps(
                {
                    "error": f"Local file not found: {local_path}",
                    "success": False,
                    "suggestion": "Check the local file path is correct and file exists",
                },
                indent=2,
            )

        # Check file size
        local_file_size = os.path.getsize(local_path)
        if local_file_size > ssh_manager.config.max_file_size:
            return json.dumps(
                {
                    "error": f"File size ({local_file_size} bytes) exceeds maximum allowed ({ssh_manager.config.max_file_size} bytes)",
                    "success": False,
                    "suggestion": "Increase MAX_FILE_SIZE environment variable or choose a smaller file",
                },
                indent=2,
            )

        # Check if host file exists (unless overwrite is true)
        if not overwrite:
            check_command = f"test -f {host_path}"
            stdout, stderr, exit_code = await ssh_manager.execute_command(check_command)
            if exit_code == 0:
                return json.dumps(
                    {
                        "error": f"File already exists on host: {host_path}",
                        "success": False,
                        "suggestion": "Set overwrite=true to replace existing file or choose a different path",
                    },
                    indent=2,
                )

        # Upload directly to host
        await ssh_manager.upload_file(local_path, host_path)

        # Set permissions on the file
        chmod_command = f"chmod {permissions} {host_path}"
        stdout, stderr, exit_code = await ssh_manager.execute_command(chmod_command)

        if exit_code != 0:
            # File was uploaded but permissions failed - not critical
            pass

        return json.dumps(
            {
                "success": True,
                "message": f"File uploaded successfully to Proxmox host",
                "local_path": local_path,
                "host_path": host_path,
                "permissions": permissions,
                "bytes_transferred": local_file_size,
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps({"error": str(e), "success": False}, indent=2)


# ============================================================================
# Health Check Middleware for HTTP Mode
# ============================================================================


async def health_check_middleware(scope, receive, send):
    """ASGI middleware that adds /health endpoint for HTTP mode

    This middleware intercepts requests to /health and returns a simple
    health check response. All other requests are passed to the MCP app.
    """
    if scope["type"] == "http" and scope["path"] == "/health":
        # Return health check response
        health_response = {
            "status": "healthy",
            "service": "proxmox-mcp-server",
            "ssh_connected": ssh_manager is not None and ssh_manager._client is not None,
        }

        response_body = json.dumps(health_response).encode("utf-8")

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(response_body)).encode()],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": response_body,
        })
    else:
        # Pass through to MCP app
        await mcp_app(scope, receive, send)


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import sys

    # Check for HTTP/SSE mode flag (HTTP is recommended in FastMCP 2.x)
    if "--http" in sys.argv or "--sse" in sys.argv:
        # Extract port from command line or use default
        port = 8000
        host = "0.0.0.0"  # Listen on all interfaces for Docker

        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
            elif arg == "--host" and i + 1 < len(sys.argv):
                host = sys.argv[i + 1]

        # Use uvicorn to run HTTP transport with custom host/port
        # This is the recommended approach for FastMCP 2.x web deployment
        print(f"Starting Proxmox MCP Server in HTTP mode on {host}:{port}")
        print(f"HTTP endpoint: http://{host}:{port}/mcp")
        print(f"Health check: http://{host}:{port}/health")
        print("")
        print("⚠️  SECURITY WARNING ⚠️")
        print("HTTP mode has NO authentication mechanism!")
        print("Anyone with network access to this endpoint can control your Proxmox infrastructure.")
        print("Recommended: Use firewall rules, VPN, or reverse proxy with authentication.")
        print("NEVER expose this endpoint directly to the internet!")
        print("")

        try:
            import uvicorn
            # Get ASGI app from FastMCP for HTTP transport
            # mcp_app is already declared as module-level variable
            mcp_app = mcp.streamable_http_app()
            # Wrap with health check middleware
            uvicorn.run(health_check_middleware, host=host, port=port)
        except ImportError:
            print("ERROR: uvicorn is required for HTTP mode")
            print("Install with: pip install uvicorn")
            sys.exit(1)
        except AttributeError:
            # Fallback: try using mcp.run() if streamable_http_app() not available
            print("INFO: Using fallback mcp.run() method")
            mcp.run()
    else:
        # Run in stdio mode (default for Claude Desktop)
        mcp.run()
