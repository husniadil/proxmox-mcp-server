# Proxmox MCP Server

Control your Proxmox LXC containers directly from Claude AI using natural language.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PEP 723](https://img.shields.io/badge/PEP-723-green.svg)](https://peps.python.org/pep-0723/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ⚠️ DISCLAIMER / PENAFIAN

**ENGLISH:**

**USE AT YOUR OWN RISK.** This software provides direct SSH access and command execution capabilities on your Proxmox infrastructure. The developer(s) of this software are **NOT responsible** for any damage, data loss, system failures, security breaches, or any other issues that may arise from using this software.

By using this software, you acknowledge that:

- You understand the risks of giving an AI system SSH access to your infrastructure
- You are solely responsible for reviewing and approving commands before execution
- You have proper backups and disaster recovery procedures in place
- You will not hold the developer(s) liable for any damages or losses

**INDONESIA:**

**GUNAKAN DENGAN RISIKO ANDA SENDIRI.** Software ini memberikan akses SSH langsung dan kemampuan eksekusi perintah pada infrastruktur Proxmox Anda. Pengembang software ini **TIDAK bertanggung jawab** atas kerusakan, kehilangan data, kegagalan sistem, pelanggaran keamanan, atau masalah lainnya yang mungkin timbul dari penggunaan software ini.

Dengan menggunakan software ini, Anda menyatakan bahwa:

- Anda memahami risiko memberikan akses SSH sistem AI ke infrastruktur Anda
- Anda sepenuhnya bertanggung jawab untuk memeriksa dan menyetujui perintah sebelum dieksekusi
- Anda memiliki backup yang memadai dan prosedur disaster recovery
- Anda tidak akan meminta pertanggungjawaban pengembang atas kerusakan atau kerugian apapun

**This software is provided "AS IS" without warranty of any kind, express or implied.**

### ✅ Enforced Risk Acceptance

**To use this software, you MUST set the environment variable:**

```bash
I_ACCEPT_RISKS=true
```

The software will **refuse to start** without this explicit acknowledgment. This ensures you have read and understood the risks before giving an AI system SSH access to your infrastructure.

---

## What is this?

This MCP (Model Context Protocol) server lets you manage Proxmox containers through Claude Desktop using natural language. Instead of SSHing into servers and typing commands, just ask Claude:

> "Check disk space on container 100"

> "Update packages on container 101"

> "Show me nginx logs from container 102"

Claude will execute the commands and show you the results.

## Features

- ✅ **Execute bash commands** inside containers
- ✅ **Manage containers** - start, stop, check status
- ✅ **List all containers** with their current state
- ✅ **Natural language interface** - no need to remember commands
- ✅ **Secure** - uses SSH with key or password authentication
- ✅ **Modern** - uses PEP 723 (no requirements.txt needed)

## Quick Start

### Prerequisites

- Proxmox VE with LXC containers
- SSH access to your Proxmox host
- Claude Desktop installed
- Python 3.10 or higher

### Installation

**Option A: Using `uv` (Recommended)**

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/husniadil/proxmox-mcp-server.git
cd proxmox-mcp-server

# Configure your Proxmox connection
cp .env.example .env
nano .env  # Add your Proxmox host details

# Test it works
uv run proxmox_mcp.py
```

**Option B: Traditional Python**

```bash
# Clone the repository
git clone https://github.com/husniadil/proxmox-mcp-server.git
cd proxmox-mcp-server

# Install dependencies
pip install mcp fastmcp paramiko pydantic python-dotenv uvicorn

# Configure your Proxmox connection
cp .env.example .env
nano .env  # Add your Proxmox host details

# Test it works
python proxmox_mcp.py
```

**Option C: Docker with HTTP Transport**

**SECURITY WARNING:** HTTP mode does NOT include any authentication mechanism. The server relies entirely on your .env file credentials for Proxmox access, but the HTTP endpoint itself is unauthenticated. This means anyone who can reach the HTTP endpoint can execute commands on your Proxmox infrastructure.

**Recommended security measures:**
- Only expose the server on localhost (127.0.0.1) or trusted networks
- Use a firewall to restrict access to the HTTP port
- Consider using a reverse proxy with authentication (nginx, Caddy, etc.)
- Use VPN or SSH tunneling for remote access
- Never expose the HTTP endpoint directly to the internet
- Keep your .env file secure and never commit it to version control

For hosting the MCP server as a web service (using HTTP/Streamable HTTP) instead of a local subprocess:

```bash
# Clone the repository
git clone https://github.com/husniadil/proxmox-mcp-server.git
cd proxmox-mcp-server

# Configure your Proxmox connection
cp .env.example .env
nano .env  # Add your Proxmox host details

# Build and run with Docker Compose
docker-compose up -d

# Check logs
docker-compose logs -f

# Stop the server
docker-compose down
```

Or using Docker directly:

```bash
# Build the image
docker build -t proxmox-mcp-server .

# Run the container
docker run -d \
  --name proxmox-mcp \
  -p 8000:8000 \
  --env-file .env \
  proxmox-mcp-server

# Check logs
docker logs -f proxmox-mcp

# Stop the container
docker stop proxmox-mcp
docker rm proxmox-mcp
```

**Important:** Environment variables are passed at runtime (not baked into the image), so the built image is safe to push to Docker registries. Credentials are only loaded when the container runs with `--env-file .env` or via docker-compose.

The server will be available at `http://localhost:8000/mcp` with HTTP transport. This is useful for:
- Remote access to the MCP server
- Running in production environments
- Integration with web applications
- Deployment in containerized infrastructure

**Note:** FastMCP 2.x uses HTTP transport (Streamable HTTP) instead of the deprecated SSE transport.

### Docker Deployment Details

**Environment Variables:**

You can configure the server using environment variables in your `.env` file or Docker Compose environment section:

```yaml
environment:
  - I_ACCEPT_RISKS=true
  - HOST=192.168.1.100
  - SSH_USERNAME=root
  - SSH_PASSWORD=your_password
  - ENABLE_HOST_EXEC=false
  - CHARACTER_LIMIT=25000
  - MAX_FILE_SIZE=10485760
```

**Using Docker Secrets (Production):**

For better security in production, use Docker secrets:

```bash
# Create secret files
echo "your_password" > ./secrets/ssh_password.txt

# Update docker-compose.yml to use secrets
# See docker-compose.yml for secret configuration examples
```

**Custom Port:**

To use a different port:

```bash
# Using Docker
docker run -d -p 9000:8000 --env-file .env proxmox-mcp-server

# Using Docker Compose (modify docker-compose.yml)
ports:
  - "9000:8000"
```

**Health Check:**

The Docker container includes a health check endpoint at `/health` that returns the server status and SSH connection state:

```bash
# Check container health
docker ps  # Look for "(healthy)" status

# Manual health check
curl http://localhost:8000/health
```

The health endpoint returns a JSON response:

```json
{
  "status": "healthy",
  "service": "proxmox-mcp-server",
  "ssh_connected": true
}
```

- `status`: Always "healthy" if the server is running
- `service`: Service identifier
- `ssh_connected`: `true` if SSH connection to Proxmox is established, `false` otherwise

**Connecting to HTTP Server:**

To connect your application to the HTTP server:

```python
# Example: Connect to MCP server via HTTP
import requests

# Health check
response = requests.get('http://localhost:8000/health')
print(response.text)

# MCP endpoint (for MCP clients)
# Use MCP client libraries to connect to http://localhost:8000/mcp
```

For MCP client connection:
```python
from mcp import Client

async with Client("http://localhost:8000/mcp") as client:
    # Use the client
    pass
```

**Note:** HTTP mode (Streamable HTTP) is designed for remote access and web integrations. For local use with Claude Desktop, use the stdio mode (Option A or B).

**IMPORTANT:** The HTTP endpoint has NO authentication. Anyone with network access to the endpoint can control your Proxmox infrastructure. Always use network isolation, firewalls, or reverse proxy authentication.

### Configuration

Edit your `.env` file:

```bash
# REQUIRED: Accept risks (see DISCLAIMER section)
I_ACCEPT_RISKS=true

# Connection details
HOST=192.168.1.100      # Your Proxmox server IP
SSH_USERNAME=root       # SSH username (NOT Proxmox UI username)
SSH_PASSWORD=your_password  # SSH password
```

Or use SSH key authentication:

```bash
# REQUIRED: Accept risks (see DISCLAIMER section)
I_ACCEPT_RISKS=true

# Connection details
HOST=192.168.1.100
SSH_USERNAME=root
SSH_KEY=/path/to/your/private_key
```

Optional configuration:

```bash
# Maximum character limit for command output (default: 25000)
# Increase for larger outputs, decrease to save tokens
CHARACTER_LIMIT=25000

# Enable host command execution (DISABLED by default for security)
# See "Host Command Execution" section for details
ENABLE_HOST_EXEC=false
```

### Add to Claude Desktop

1. Open Claude Desktop configuration:
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

2. Add this configuration (adjust the path to your installation):

```json
{
  "mcpServers": {
    "proxmox": {
      "command": "uv",
      "args": ["run", "/full/path/to/proxmox_mcp.py"],
      "env": {
        "I_ACCEPT_RISKS": "true",
        "HOST": "192.168.1.100",
        "SSH_USERNAME": "root",
        "SSH_PASSWORD": "your_password"
      }
    }
  }
}
```

**IMPORTANT:** You MUST set `"I_ACCEPT_RISKS": "true"` after reading the DISCLAIMER section.

Or if not using `uv`:

```json
{
  "mcpServers": {
    "proxmox": {
      "command": "python",
      "args": ["/full/path/to/proxmox_mcp.py"],
      "env": {
        "I_ACCEPT_RISKS": "true",
        "HOST": "192.168.1.100",
        "SSH_USERNAME": "root",
        "SSH_PASSWORD": "your_password"
      }
    }
  }
}
```

3. Restart Claude Desktop

4. Test by asking Claude:
   ```
   List my Proxmox containers
   ```

## Usage Examples

Once configured, you can use natural language to manage your containers:

### Basic Commands

```
Show me all my containers
```

```
Check the status of container 100
```

```
Start container 101
```

```
Stop container 102
```

### System Administration

```
Check disk space and memory usage on container 100
```

```
Show me the last 50 lines of syslog on container 101
```

```
List all running processes on container 102
```

### Software Management

```
Update package lists on container 100
```

```
Install nginx on container 101
```

```
Check if nginx is running on container 102
```

### File Operations

```
Show me the contents of /etc/nginx/nginx.conf on container 100
```

```
List files in /var/www on container 101
```

```
Check the size of /var/log directory on container 102
```

## How It Works

```
You → Claude Desktop → MCP Server → SSH → Proxmox Host → pct exec → Container
```

1. You ask Claude a question about your container
2. Claude calls the appropriate MCP tool
3. The MCP server connects to Proxmox via SSH
4. Uses `pct exec` command to run commands inside containers
5. Returns the results to Claude
6. Claude shows you the results in natural language

## Available Tools

The server provides 10 tools that Claude can use:

### Container Tools

1. **proxmox_container_exec_command** - Execute any bash command in a container
2. **proxmox_list_containers** - List all containers with their status
3. **proxmox_container_status** - Check if a container is running or stopped
4. **proxmox_start_container** - Start a stopped container
5. **proxmox_stop_container** - Stop a running container

### File Transfer Tools

6. **proxmox_download_file_from_container** - Download files from container to local machine
7. **proxmox_upload_file_to_container** - Upload files from local machine to container
8. **proxmox_download_file_from_host** - Download files from Proxmox host (⚠️ requires ENABLE_HOST_EXEC)
9. **proxmox_upload_file_to_host** - Upload files to Proxmox host (⚠️ requires ENABLE_HOST_EXEC)

### Host Tools

10. **proxmox_host_exec_command** - Execute commands directly on the Proxmox host (⚠️ DISABLED by default)

Claude will automatically choose which tool to use based on your question.

## File Transfer Operations

The MCP server supports transferring files between your local machine and Proxmox containers or the host system.

### How It Works

**Container File Transfers:**

```
Local Machine ←→ SFTP ←→ Proxmox Host ←→ pct pull/push ←→ Container
```

**Host File Transfers:**

```
Local Machine ←→ SFTP ←→ Proxmox Host
```

### Configuration

Add to your `.env` file (optional):

```bash
# Maximum file size in bytes (default: 10MB)
MAX_FILE_SIZE=10485760  # 10 MB
```

### Container File Operations

**Download from Container:**

```
Download /etc/nginx/nginx.conf from container 100 to ./nginx.conf
```

**Upload to Container:**

```
Upload ./config.yaml to container 101 at /etc/app/config.yaml with permissions 644
```

Claude will automatically:

- Check file sizes against MAX_FILE_SIZE limit
- Prevent overwriting files (unless you specify overwrite: true)
- Use temporary staging on the Proxmox host
- Clean up temporary files automatically
- Set proper file permissions

### Host File Operations

⚠️ **Requires `ENABLE_HOST_EXEC=true`** - See [Host Command Execution](#host-command-execution) section.

**Download from Host:**

```
Download /etc/pve/storage.cfg from the Proxmox host to ./storage.cfg
```

**Upload to Host:**

```
Upload ./backup.sh to Proxmox host at /root/backup.sh with permissions 755
```

### File Transfer Examples

**Download Configuration Files:**

```
Download nginx configuration from container 100
Get the application log from container 101 at /var/log/app.log
Backup /etc/hosts file from container 102
```

**Upload Configuration Files:**

```
Upload my local nginx.conf to container 100 at /etc/nginx/nginx.conf
Deploy script.sh to container 101 at /root/script.sh with executable permissions
```

**Backup and Restore:**

```
Download database backup from container 100 at /backups/db.sql
Upload the restored database to container 100 at /tmp/restore.sql
```

### File Size Limits

Default maximum file size is **10 MB** to prevent:

- Memory exhaustion
- Excessive token usage
- Long transfer times

To adjust the limit:

```bash
# In your .env file
MAX_FILE_SIZE=52428800  # 50 MB
```

### Security Considerations

File transfers include these safety features:

✅ **Path Validation** - Prevents directory traversal attacks (no `..` allowed)
✅ **Size Limits** - Enforces MAX_FILE_SIZE to prevent resource exhaustion
✅ **Overwrite Protection** - Won't overwrite existing files unless explicitly allowed
✅ **Permission Control** - Sets specific file permissions on upload
✅ **Temp File Cleanup** - Automatically removes temporary files even on errors
✅ **Host Access Control** - Host file operations require ENABLE_HOST_EXEC flag

⚠️ **Important Notes:**

- Files are transferred through the Proxmox host (requires temp space)
- Container must be running for container file operations
- Uploading to host requires ENABLE_HOST_EXEC=true
- Always review file paths before confirming operations

### Troubleshooting File Transfers

**Error: "File too large"**

- Solution: Increase MAX_FILE_SIZE in your .env file

**Error: "Local file already exists"**

- Solution: Either delete the local file or set overwrite=true

**Error: "Permission denied"**

- Solution: Check SSH user has access to the file path

**Error: "Container not running"**

- Solution: Start the container first using `proxmox_start_container`

**Error: "Host file operations are DISABLED"**

- Solution: Set ENABLE_HOST_EXEC=true to enable host file transfers

## Host Command Execution

### ⚠️ What is Host Exec?

**Host exec** allows you to run commands directly on your Proxmox host, not inside containers. This gives you full access to:

- System-wide operations (cluster status, storage management)
- Creating/managing containers and VMs
- Host system resources and diagnostics
- Proxmox-specific commands (pct, qm, pvecm, etc.)

### 🔐 Security Warning

**This feature is EXTREMELY powerful and potentially dangerous!**

| Aspect                | Container Exec         | Host Exec                     |
| --------------------- | ---------------------- | ----------------------------- |
| **Scope**             | Single container       | **Entire infrastructure**     |
| **Isolation**         | Protected by container | **None - full system access** |
| **Impact**            | One service            | **ALL containers/VMs**        |
| **Risk Level**        | Medium                 | **🔴 VERY HIGH**              |
| **Can break Proxmox** | No                     | **YES**                       |
| **Default state**     | Enabled                | **DISABLED**                  |

### 🚀 How to Enable

Host exec is **DISABLED by default** for safety. To enable:

**Option 1: Via .env file**

```bash
# Add to your .env file
ENABLE_HOST_EXEC=true
```

**Option 2: Via Claude Desktop config**

```json
{
  "mcpServers": {
    "proxmox": {
      "command": "uv",
      "args": ["run", "/path/to/proxmox_mcp.py"],
      "env": {
        "I_ACCEPT_RISKS": "true",
        "HOST": "192.168.1.100",
        "SSH_USERNAME": "root",
        "SSH_PASSWORD": "your_password",
        "ENABLE_HOST_EXEC": "true"
      }
    }
  }
}
```

After enabling, restart Claude Desktop.

### 📊 When to Use Host vs Container Exec

**Use Host Exec (`proxmox_host_exec_command`) for:**

- ✅ Listing all containers/VMs: `pct list`, `qm list`
- ✅ Checking cluster status: `pvecm status`
- ✅ Host resources: `df -h`, `free -h` (host level)
- ✅ Storage management: `pvesm status`, `zpool status`, `zfs list`
- ✅ Creating containers/VMs: `pct create`, `qm create`
- ✅ Proxmox services: `systemctl status pveproxy`
- ✅ Network diagnostics on the host

**Use Container Exec (`proxmox_container_exec_command`) for:**

- ✅ Running commands inside a specific container
- ✅ Installing software in a container
- ✅ Checking logs inside a container
- ✅ Managing services inside a container
- ✅ File operations inside a container

### 🎯 Command Safety Levels

**✅ SAFE (Read-Only Commands)**

These commands only read information and cannot harm your system:

```bash
# List containers and VMs
pct list
qm list

# Check cluster status
pvecm status

# Host resources
df -h
free -h
uptime
who

# Storage information
pvesm status
zpool status
zfs list

# Network info
ip addr
ip route
```

**⚠️ MODERATE RISK**

These commands make changes but are generally safe:

```bash
# Container lifecycle
pct create <vmid> <template> ...
pct start <vmid>
pct stop <vmid>
qm start <vmid>
qm stop <vmid>

# Service management
systemctl restart pveproxy
systemctl status pvedaemon

# Package management
apt update
```

**🔴 HIGH RISK**

These commands can cause service disruptions:

```bash
# Destructive operations
pct destroy <vmid>
qm destroy <vmid>

# System changes
apt upgrade -y
apt dist-upgrade

# Service stops
systemctl stop pveproxy

# System control
shutdown -h now
reboot
```

**⛔ DANGEROUS - AVOID**

These commands can destroy your entire system:

```bash
# File deletion
rm -rf /
rm -rf /var
rm -rf /etc

# Disk operations
dd if=/dev/zero of=/dev/sda
mkfs.ext4 /dev/sda1

# Device operations
Commands affecting /dev/*
```

### 💡 Usage Examples

Once host exec is enabled, you can ask Claude:

**System Status:**

```
Show me all containers and VMs on my Proxmox host
Check my cluster status
What's the disk usage on the Proxmox host?
```

**Storage Management:**

```
Show me my ZFS pool status
List all storage on Proxmox
Check the health of my storage
```

**Container Management:**

```
Create a new Ubuntu container with ID 200
List all stopped containers
Show me system resource usage on the host
```

**Diagnostics:**

```
Check if Proxmox services are running
Show me network interfaces on the host
What's the uptime of my Proxmox server?
```

### 🛡️ Best Practices

1. **Start with read-only commands** - Get comfortable with `pct list`, `df -h`, etc. first
2. **Enable only when needed** - Keep `ENABLE_HOST_EXEC=false` when not actively using host commands
3. **Review before executing** - Always review what Claude is about to run, especially for destructive operations
4. **Use container exec when possible** - If your task can be done inside a container, use container exec instead
5. **Backup first** - Before making major changes, ensure you have backups
6. **Test in dev environment** - Try commands in a test environment before production
7. **Monitor logs** - Keep an eye on system logs when running host commands
8. **Understand the command** - If Claude suggests a command you don't understand, ask for explanation first

### 🚨 Emergency Recovery

If you accidentally run a dangerous command:

1. **Stop immediately** - If the command is still running, you may be able to stop it via SSH
2. **Check damage** - Run `df -h`, `systemctl status`, `pct list` to assess
3. **Restore from backup** - Use Proxmox backup tools to restore if needed
4. **Seek help** - Proxmox forums and community can help with recovery

### ❓ Troubleshooting

**Error: "Host command execution is DISABLED for safety"**

Solution: Enable host exec by setting `ENABLE_HOST_EXEC=true` in your configuration.

**Error: "Permission denied"**

Solution: Ensure your SSH user has the necessary permissions (root usually has all permissions).

**Command hangs/takes too long**

Solution: Increase the timeout parameter in your request, or check if the host is responsive.

## Security

⚠️ **CRITICAL: Please read the [DISCLAIMER](#️-disclaimer--penafian) section first!**

⚠️ **Important Security Notes:**

- This server has **full shell access** to your containers and potentially your Proxmox host
- Commands are executed as the SSH user (typically root) with **full privileges**
- An AI system will have direct access to execute commands on your infrastructure
- **YOU are responsible** for reviewing commands before they execute
- **The developer is NOT responsible** for any damage or data loss
- Use SSH keys instead of passwords when possible
- Keep your `.env` file secure (it's in `.gitignore`)
- Only allow SSH access from trusted networks
- Review logs regularly to monitor activity
- **Always have backups** before using this tool in production

**Built-in Security Features:**

- ✅ Input validation on all parameters
- ✅ Command timeout limits (max 300 seconds)
- ✅ No credentials stored in code
- ✅ Environment-based configuration
- ✅ SSH connection lifecycle management

## Troubleshooting

### Can't connect to Proxmox

**Error:** `Failed to connect to Proxmox host`

**Solutions:**

- Verify `HOST` is correct
- Check SSH port (default is 22)
- Test SSH manually: `ssh root@your-proxmox-host`
- Check firewall rules

### Container not found

**Error:** `Container {vmid} not found`

**Solutions:**

- Ask Claude to list all containers first
- Verify the container ID is correct
- Check if the container exists in Proxmox web UI

### Permission denied

**Error:** `Permission denied`

**Solutions:**

- Verify SSH credentials are correct
- Make sure the user has permission to run `pct` commands
- Root user typically has all required permissions

### Command timeout

**Error:** `Command execution timeout`

**Solutions:**

- Some commands take longer (e.g., `apt upgrade`)
- You can increase timeout in your request
- Check if the container is responsive

## Why SSH Instead of Proxmox API?

After researching the Proxmox API, we found that:

- ❌ Proxmox API does **NOT** support direct command execution in containers
- ❌ The `/nodes/{node}/execute` endpoint is for API calls, not shell commands
- ✅ `pct exec` via SSH is the **official recommended method**
- ✅ Works with existing Proxmox setup without additional configuration
- ✅ Provides full bash access to containers

## Technical Details

- **Language:** Python 3.10+
- **Framework:** FastMCP (Model Context Protocol)
- **SSH Library:** Paramiko
- **Validation:** Pydantic v2
- **Format:** PEP 723 (inline dependencies)

### Project Structure

```
proxmox-mcp-server/
├── proxmox_mcp.py                      # Main MCP server (PEP 723)
├── .env.example                        # Configuration template
├── stack.env                           # Stack/Portainer environment template
├── claude_desktop_config.example.json  # Claude Desktop config example
├── Dockerfile                          # Docker image definition
├── docker-compose.yml                  # Docker Compose configuration
├── .dockerignore                       # Docker build exclusions
└── README.md                           # This file
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details

## Support

- **Issues:** [GitHub Issues](https://github.com/husniadil/proxmox-mcp-server/issues)
- **Discussions:** [GitHub Discussions](https://github.com/husniadil/proxmox-mcp-server/discussions)

## Acknowledgments

- Built with [FastMCP](https://github.com/jlowin/fastmcp)
- Follows [Model Context Protocol](https://modelcontextprotocol.io/) specification
- Uses [Paramiko](https://www.paramiko.org/) for SSH connections

## Related Projects

- [MCP Servers](https://github.com/modelcontextprotocol/servers) - Official MCP servers
- [Claude Desktop](https://claude.ai/download) - AI assistant by Anthropic

---

**Made with ❤️ for the Proxmox and Claude community**

⭐ If you find this useful, please star the repository!
