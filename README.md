# MudaleTunnel
![image](https://github.com/user-attachments/assets/69ab63fd-533d-4fb9-b704-1be00d4f6001)

## Description

MudaleTunnel is a powerful **SSH tunnel management tool** that simplifies the process of setting up and managing SSH tunnels to exposed services on remote machines. It automates the detection of open ports and services using **`nmap`**, and provides both a **command-line interface (CLI)** and a **modern web interface** for creating static port forwarding tunnels (`ssh -L`) and dynamic SOCKS proxy tunnels (`ssh -D`). This tool is particularly useful for penetration testers, system administrators, security researchers, or anyone needing to securely access services behind firewalls.

---

## Features

* **Local IP Detection:** Automatically identifies your local IP address for tunnel configuration
* **OS Compatibility Check:** Detects the operating system (Linux, Windows, macOS) to tailor `nmap` installation commands
* **Automated Nmap Installation:** Checks for `nmap` and installs it if missing, using appropriate package managers
* **Comprehensive Service Scanning:** Performs full `nmap` scans (`-p- -sV`) to identify all open ports and services
* **Static SSH Tunneling:** Local port forwarding (`ssh -L`) to forward specific ports to remote services
* **Dynamic SSH Tunneling:** SOCKS proxy (`ssh -D`) for dynamic routing of traffic through SSH server
* **Tunnel Management:** Create, list, stop, and monitor multiple simultaneous tunnels
* **Web Interface:** Modern dark-themed web UI with real-time tunnel status, logs, and metrics
* **Real-time Updates:** WebSocket support for live tunnel status monitoring
* **Tunnel Logs & Metrics:** Track tunnel activity, uptime, and health status
* **Cross-platform Support:** Works on Windows, Linux, and macOS

---

## Prerequisites

Before running MudaleTunnel, ensure you have:

* **Python 3.8+:** The script is written and tested with Python 3.8 and above
* **Internet Connection:** Required for installing `nmap` and Python dependencies
* **SSH Client:** Your system should have an SSH client installed (usually pre-installed on Linux/macOS, available via Git Bash or PuTTY on Windows)
* **Nmap:** Will be automatically installed if missing (requires admin/sudo privileges)

---

## Installation

### Method 1: Direct Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/TarzEH/MudaleTunnel.git
   cd MudaleTunnel
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

   *Note: The script will attempt to install `nmap` automatically if it's not found on your system.*

### Method 2: Docker Installation (Recommended)

**Using Docker Compose:**
```bash
docker-compose up -d
```

Access the web interface at `http://localhost:8000`

<<<<<<< HEAD
## Usage

### Interactive Mode (Default)
=======
**Using Docker directly:**
```bash
docker build -t mudaletunnel .
docker run -d -p 8000:8000 mudaletunnel
```

See [README_DOCKER.md](README_DOCKER.md) for detailed Docker instructions.

---

## Quick Start

### CLI Mode
>>>>>>> 621a974 (Major update: Add static/dynamic SSH tunneling, web interface, Docker support, and dark theme)
```bash
python main.py interactive
# or simply
python main.py
```

<<<<<<< HEAD
### Command Line Arguments
```bash
# Scan only
python main.py scan 192.168.1.1

# Full tunnel setup
python main.py scan 192.168.1.1 --user myuser --ssh-host 10.0.0.1 --port 80 --local-port 8080

# Available options:
#   --user, -u        SSH username
#   --ssh-host, -s    SSH hostname or IP
#   --port, -p        Specific port to tunnel
#   --local-port, -l  Local port for tunneling
```

### Linux Installation
1. Download the latest release: `mudaletunnel-linux-v*.tar.gz`
2. Extract: `tar -xzf mudaletunnel-linux-v*.tar.gz`
3. Install: `cd linux && sudo ./install.sh`
4. Run: `mudaletunnel scan 192.168.1.1`

To run MudaleTunnel, execute the Python script from your terminal:

The tool will guide you through the following steps:
=======
### Web Interface Mode
```bash
python main.py web
```
Then open `http://localhost:8000` in your browser.
>>>>>>> 621a974 (Major update: Add static/dynamic SSH tunneling, web interface, Docker support, and dark theme)

---

## Command-Line Arguments

### Main Commands

```bash
python main.py [COMMAND] [OPTIONS]
```

**Available Commands:**

| Command | Description |
|---------|-------------|
| `cli` | Run in CLI mode (interactive) |
| `web` | Run in web interface mode |
| *(none)* | Defaults to CLI mode if no command specified |

**Web Interface Options:**

```bash
python main.py web [OPTIONS]
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--port` | `-p` | Port for web server | `8000` |
| `--host` | `-h` | Host for web server | `127.0.0.1` |

**Examples:**
```bash
# Run web interface on default port 8000
python main.py web

# Run web interface on custom port
python main.py web --port 8080

# Run web interface on custom host and port
python main.py web --host 0.0.0.0 --port 9000

# Run CLI mode explicitly
python main.py cli
```

---

## Usage Guide

## CLI Mode Usage

### Starting CLI Mode

```bash
python main.py
# or
python main.py cli
```

### Step-by-Step CLI Workflow

#### 1. Initial Setup

When you start MudaleTunnel, you'll see:
```
[Logo Display]
[Your Local IP Address]
Operating System: [Your OS]
```

#### 2. Main Menu

```
MudaleTunnel Main Menu:
1. Scan target and create tunnel
2. Manage existing tunnels
0. Exit

Enter your choice:
```

**Option 1: Scan and Create Tunnel**

1. **Enter target to scan:**
   ```
   Enter the target IP or domain to scan: 192.168.1.100
   ```

2. **Nmap scan runs automatically:**
   ```
   Starting full nmap scan on 192.168.1.100...
   ```
   
   Results displayed in a table:
   ```
   ┏━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━┓
   ┃ Port          ┃ State   ┃ Service    ┃
   ┡━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━┩
   │ 22/tcp        │ open    │ ssh        │
   │ 80/tcp        │ open    │ http       │
   │ 443/tcp       │ open    │ https      │
   └───────────────┴─────────┴────────────┘
   ```

3. **Enter SSH credentials:**
   ```
   Enter the SSH username: admin
   Enter the SSH hostname or IP address: jumpbox.example.com
   ```

4. **Choose tunneling mode:**
   ```
   Select tunneling mode:
   1. Static tunneling (Local port forwarding - ssh -L)
   2. Dynamic tunneling (SOCKS proxy - ssh -D)
   3. Manage existing tunnels
   0. Exit

   Enter your choice: 1
   ```

#### 3. Static Tunneling (Port Forwarding)

**Example: Forwarding HTTP service**

```
Available services for tunneling:
1. Port: 22/tcp, Service: ssh
2. Port: 80/tcp, Service: http
3. Port: 443/tcp, Service: https

Select a service number (0 to cancel): 2
Selected Service: http on Port: 80/tcp

Enter local port (default 80): 8080
Execute tunnel automatically? (yes/no, default: no): yes

✓ Static tunnel created successfully!
Tunnel ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
Local port: 8080 -> Remote: 192.168.1.100:80
```

**What happened:**
- Created SSH tunnel: `ssh -L 8080:192.168.1.100:80 admin@jumpbox.example.com -N -f`
- Tunnel is now active and running in background
- You can access `http://localhost:8080` to reach the remote HTTP service

**Example: Forwarding multiple ports**

You can create multiple tunnels by repeating the process. Each tunnel runs independently.

#### 4. Dynamic Tunneling (SOCKS Proxy)

**Example: Creating a SOCKS proxy**

```
Select tunneling mode:
1. Static tunneling (Local port forwarding - ssh -L)
2. Dynamic tunneling (SOCKS proxy - ssh -D)
3. Manage existing tunnels
0. Exit

Enter your choice: 2

Dynamic Tunneling (SOCKS Proxy)
Enter local SOCKS port (default: auto): 1080
Execute tunnel automatically? (yes/no, default: no): yes

✓ Dynamic tunnel (SOCKS proxy) created successfully!
Tunnel ID: b2c3d4e5-f6a7-8901-bcde-f12345678901
SOCKS proxy listening on port: 1080

To use the SOCKS proxy:
  - Firefox: Settings > Network Settings > Manual proxy > SOCKS Host: 127.0.0.1, Port: 1080
  - curl: curl --socks5 127.0.0.1:1080 http://example.com
  - Environment: export HTTP_PROXY=socks5://127.0.0.1:1080
```

**What happened:**
- Created SOCKS proxy: `ssh -D 1080 admin@jumpbox.example.com -N -f`
- SOCKS proxy is active on port 1080
- All traffic through this proxy will be routed through the SSH server

#### 5. Tunnel Management

**Accessing Management Menu:**

From main menu, select option 2:
```
MudaleTunnel Main Menu:
1. Scan target and create tunnel
2. Manage existing tunnels
0. Exit

Enter your choice: 2
```

**Management Options:**

```
Tunnel Management:
1. List all tunnels
2. Stop a tunnel
3. Stop all tunnels
4. Check tunnel health
0. Back

Enter your choice: 1
```

**Example: Listing All Tunnels**

```
┏━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━┓
┃ ID            ┃ Type   ┃ Local Port ┃ Remote                ┃ Status  ┃ PID   ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━┩
│ a1b2c3d4      ┃ STATIC │ 8080      │ 192.168.1.100:80     │ active  │ 12345 │
│ b2c3d4e5      ┃ DYNAMIC│ 1080      │ SOCKS Proxy           │ active  │ 12346 │
└───────────────┴────────┴───────────┴───────────────────────┴─────────┴───────┘
```

**Example: Stopping a Tunnel**

```
Tunnel Management:
1. List all tunnels
2. Stop a tunnel
3. Stop all tunnels
4. Check tunnel health
0. Back

Enter your choice: 2

[List of tunnels displayed...]

Enter tunnel ID to stop: a1b2c3d4
✓ Tunnel a1b2c3d4 stopped successfully.
```

**Example: Checking Tunnel Health**

```
Tunnel Management:
1. List all tunnels
2. Stop a tunnel
3. Stop all tunnels
4. Check tunnel health
0. Back

Enter your choice: 4

[List of tunnels displayed...]

Enter tunnel ID to check: a1b2c3d4

Tunnel Health:
  Healthy: True
  Process Running: True
  Port Listening: True
```

**Example: Stopping All Tunnels**

```
Tunnel Management:
1. List all tunnels
2. Stop a tunnel
3. Stop all tunnels
4. Check tunnel health
0. Back

Enter your choice: 3

Are you sure you want to stop all tunnels? (yes/no): yes
✓ Stopped 2 tunnel(s).
```

---

## Web Interface Usage

### Starting Web Interface

```bash
python main.py web
# or with custom port
python main.py web --port 8080
```

Then open your browser at `http://localhost:8000` (or your custom port).

### Web Interface Features

#### 1. Target Scanning

**Step 1: Enter Target**
- In the "Target Scanning" section, enter an IP address or domain name
- Example: `192.168.1.100` or `example.com`

**Step 2: Click Scan**
- Click the "Scan" button
- Progress bar appears showing scan status
- Status messages update in real-time

**Step 3: View Results**
- Discovered services appear in the "Discovered Services" section
- Each service shows: Port, Service name, State
- Click "Use for Tunnel" to pre-fill tunnel creation form

**Example:**
```
Target: 192.168.1.100
[Scan Button]

Status: Scan completed!

Discovered Services:
┌─────────────────────────────────────────────┐
│ Port: 22/tcp | Service: ssh | State: open  │ [Use for Tunnel]
│ Port: 80/tcp | Service: http | State: open │ [Use for Tunnel]
│ Port: 443/tcp | Service: https | State: open│ [Use for Tunnel]
└─────────────────────────────────────────────┘
```

#### 2. Creating Static Tunnels

**Step 1: Switch to Static Tab**
- Click "Static (Port Forward)" tab

**Step 2: Fill Form**
```
SSH Username: admin
SSH Host: jumpbox.example.com
Target Host: 192.168.1.100
Remote Port: 80
Local Port (optional): 8080
☑ Execute tunnel automatically
```

**Step 3: Submit**
- Click "Create Static Tunnel"
- Success notification appears
- Tunnel appears in "Active Tunnels" section

**Example Result:**
```
✓ Static tunnel created successfully!

Active Tunnels:
┌─────────────────────────────────────────────────────────┐
│ [STATIC] [ACTIVE]                    ID: a1b2c3d4       │
│ Local Port: 8080                                       │
│ Remote: 192.168.1.100:80                               │
│ SSH: admin@jumpbox.example.com                         │
│ PID: 12345                                             │
│ [Details] [Logs] [Metrics] [Stop]                      │
└─────────────────────────────────────────────────────────┘
```

#### 3. Creating Dynamic Tunnels

**Step 1: Switch to Dynamic Tab**
- Click "Dynamic (SOCKS Proxy)" tab

**Step 2: Fill Form**
```
SSH Username: admin
SSH Host: jumpbox.example.com
Local SOCKS Port (optional): 1080
☑ Execute tunnel automatically
```

**Step 3: Submit**
- Click "Create Dynamic Tunnel"
- Success notification appears with usage instructions

**Example Result:**
```
✓ Dynamic tunnel (SOCKS proxy) created successfully!

To use the SOCKS proxy:
  - Firefox: Settings > Network Settings > Manual proxy > 
    SOCKS Host: 127.0.0.1, Port: 1080
  - curl: curl --socks5 127.0.0.1:1080 http://example.com
  - Environment: export HTTP_PROXY=socks5://127.0.0.1:1080
```

#### 4. Managing Tunnels

**Viewing Active Tunnels:**
- All active tunnels are displayed in the "Active Tunnels" section
- Real-time status updates via WebSocket
- Color-coded status indicators (green=active, red=stopped)

**Tunnel Actions:**

1. **Details:** View full tunnel configuration and SSH command
2. **Logs:** View tunnel logs in real-time
3. **Metrics:** View tunnel metrics (uptime, status checks, etc.)
4. **Stop:** Stop the tunnel

**Example: Viewing Tunnel Details**

Click "Details" on any tunnel:
```
Tunnel Details
─────────────────────────────────────
Type: static
Status: active
Local Port: 8080
Remote Host: 192.168.1.100
Remote Port: 80
SSH User: admin
SSH Host: jumpbox.example.com
PID: 12345
Created: 2024-01-12 14:30:00

Command:
ssh -L 8080:192.168.1.100:80 admin@jumpbox.example.com -N -f
```

**Example: Viewing Tunnel Logs**

Click "Logs" on any tunnel:
```
[2024-01-12T14:30:00] [INFO] Static tunnel created: 8080 -> 192.168.1.100:80
[2024-01-12T14:30:05] [INFO] Tunnel health check: healthy
[2024-01-12T14:35:00] [INFO] Tunnel status: active
```

**Example: Viewing Tunnel Metrics**

Click "Metrics" on any tunnel:
```
┌──────────────┬──────────────┬──────────────┐
│ 2h 15m 30s   │     45       │ 2024-01-12   │
│ Uptime       │ Status Checks│ Created      │
└──────────────┴──────────────┴──────────────┘
```

**Stopping Tunnels:**

- **Stop Individual:** Click "Stop" button on specific tunnel
- **Stop All:** Click "Stop All" button in tunnel actions section

#### 5. Real-time Updates

The web interface uses WebSocket for real-time updates:
- Tunnel status changes appear instantly
- New tunnels appear automatically
- Stopped tunnels update in real-time
- No page refresh needed

---

## Feature Examples

### Example 1: Accessing Internal Web Server

**Scenario:** You need to access an internal web server at `192.168.1.100:80` through a jump box.

**CLI Method:**
```bash
python main.py
# Select: 1. Scan target and create tunnel
# Enter target: 192.168.1.100
# Enter SSH username: admin
# Enter SSH host: jumpbox.example.com
# Select: 1. Static tunneling
# Select service: 2 (http on port 80)
# Local port: 8080
# Execute: yes
```

**Web Method:**
1. Enter target `192.168.1.100` and scan
2. Click "Use for Tunnel" on HTTP service
3. Fill form: SSH user, host, target, ports
4. Click "Create Static Tunnel"

**Result:**
- Access `http://localhost:8080` to reach the internal web server

### Example 2: Creating SOCKS Proxy for Browsing

**Scenario:** You need to browse the internet through a remote SSH server.

**CLI Method:**
```bash
python main.py
# Select: 1. Scan target and create tunnel
# Enter SSH username: user
# Enter SSH host: proxy.example.com
# Select: 2. Dynamic tunneling
# Local port: 1080
# Execute: yes
```

**Web Method:**
1. Switch to "Dynamic (SOCKS Proxy)" tab
2. Fill SSH credentials
3. Set port 1080 (or leave auto)
4. Click "Create Dynamic Tunnel"

**Result:**
- Configure browser to use SOCKS5 proxy at `127.0.0.1:1080`
- All browser traffic routes through the SSH server

### Example 3: Multiple Port Forwards

**Scenario:** You need to forward SSH (22), HTTP (80), and MySQL (3306) ports.

**CLI Method:**
```bash
python main.py
# Repeat tunnel creation for each service:
# 1. Create tunnel for port 22 → local 2222
# 2. Create tunnel for port 80 → local 8080
# 3. Create tunnel for port 3306 → local 3306
```

**Web Method:**
1. Scan target to discover services
2. Create tunnel for SSH (use "Use for Tunnel" button)
3. Create tunnel for HTTP
4. Create tunnel for MySQL
5. All tunnels appear in "Active Tunnels" section

**Result:**
- Multiple tunnels running simultaneously
- Each accessible on its local port

### Example 4: Monitoring Tunnel Health

**Scenario:** You want to check if your tunnels are still active.

**CLI Method:**
```bash
python main.py
# Select: 2. Manage existing tunnels
# Select: 4. Check tunnel health
# Enter tunnel ID
```

**Web Method:**
1. View "Active Tunnels" section
2. Status indicators show active/stopped
3. Click "Metrics" for detailed health info
4. Real-time updates via WebSocket

**Result:**
- Health status: Process running, port listening
- Uptime and metrics displayed

---

## Advanced Usage

### Running Multiple Instances

You can run both CLI and web interface simultaneously by using different terminals:

**Terminal 1 (Web):**
```bash
python main.py web --port 8000
```

**Terminal 2 (CLI):**
```bash
python main.py cli
```

Both share the same tunnel manager, so tunnels created in one interface appear in the other.

### Using SSH Keys

MudaleTunnel uses your system's SSH configuration. To use SSH keys:

1. **Ensure SSH keys are set up:**
   ```bash
   ssh-keygen -t rsa -b 4096
   ssh-copy-id user@remote-host
   ```

2. **Use key-based authentication:**
   - MudaleTunnel will automatically use your SSH keys
   - No password prompts if keys are configured

### Custom SSH Options

MudaleTunnel generates standard SSH commands. To add custom options, you can:

1. **Generate command only (don't execute):**
   - In CLI: Answer "no" to "Execute tunnel automatically?"
   - In Web: Uncheck "Execute tunnel automatically"
   - Copy the generated command and modify it

2. **Example with custom options:**
   ```bash
   # Generated command:
   ssh -L 8080:192.168.1.100:80 user@host -N -f
   
   # Modified with custom options:
   ssh -L 8080:192.168.1.100:80 user@host -N -f -o ServerAliveInterval=60
   ```

---

## Troubleshooting

### Common Issues

**Issue: "nmap is not installed"**
- **Solution:** MudaleTunnel will attempt to install it automatically. On Linux/macOS, you may need `sudo` privileges. On Windows, ensure Chocolatey is installed.

**Issue: "Port already in use"**
- **Solution:** Choose a different local port, or stop the process using that port.

**Issue: "SSH connection failed"**
- **Solution:** 
  - Verify SSH credentials are correct
  - Check SSH server is accessible
  - Ensure SSH keys are properly configured
  - Test SSH connection manually: `ssh user@host`

**Issue: "Tunnel process died"**
- **Solution:**
  - Check SSH connection is stable
  - Verify remote host is accessible
  - Check tunnel logs for error messages
  - Recreate the tunnel

**Issue: "Web interface not accessible"**
- **Solution:**
  - Check if port is already in use
  - Try a different port: `python main.py web --port 8080`
  - Ensure firewall allows the port
  - Check if host is correct (use `0.0.0.0` for network access)

**Issue: "Tunnel not working"**
- **Solution:**
  - Verify tunnel is active: Check tunnel status
  - Test local port: `curl http://localhost:8080` (for HTTP)
  - Check tunnel health in management menu
  - Review tunnel logs for errors

### Getting Help

- Check tunnel logs for detailed error messages
- Use tunnel health check feature
- Verify SSH connection works manually
- Review system logs for SSH errors

---

## Best Practices

1. **Use SSH Keys:** Set up SSH key authentication to avoid password prompts
2. **Monitor Tunnels:** Regularly check tunnel health, especially for long-running tunnels
3. **Clean Up:** Stop unused tunnels to free up ports
4. **Security:** Only create tunnels to trusted hosts
5. **Port Management:** Use consistent port numbering for easier management
6. **Logs:** Review tunnel logs if experiencing issues

---

## Dependencies

* `typer`: For building the command-line interface
* `rich`: For beautiful terminal output and progress bars
* `typing_extensions`: For advanced type hints
* `fastapi`: For web interface backend
* `uvicorn`: ASGI server for FastAPI
* `websockets`: For real-time WebSocket updates
* `jinja2`: For HTML templating

See `requirements.txt` for complete list with versions.

---

## Contributing

Contributions are welcome! If you have suggestions for improvements, new features, or bug fixes, please feel free to open an [issue](https://github.com/TarzEH/MudaleTunnel/issues) or submit a [pull request](https://github.com/TarzEH/MudaleTunnel/pulls).

---

## License

This project is open-source and available under the [MIT License](https://opensource.org/licenses/MIT).

---

## Acknowledgments

Built with ❤️ for the security and sysadmin community.
