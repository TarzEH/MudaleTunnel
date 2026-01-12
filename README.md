# MudaleTunnel v2.0
![image](https://github.com/user-attachments/assets/69ab63fd-533d-4fb9-b704-1be00d4f6001)

## 🎯 Description

**MudaleTunnel** is a powerful **red team SSH tunnel management tool** that simplifies the process of setting up and managing SSH tunnels to exposed services on remote machines. It automates the detection of open ports and services using **`nmap`**, and provides both a **command-line interface (CLI)** and a **modern web interface** for creating all types of SSH tunnels.

### Supported SSH Tunneling Techniques

1. **Static Tunneling (`ssh -L`)** - Local port forwarding for direct service access
2. **Dynamic Tunneling (`ssh -D`)** - SOCKS proxy for flexible routing
3. **Remote Tunneling (`ssh -R`)** - Reverse port forwarding when firewall blocks inbound
4. **Remote Dynamic Tunneling (`ssh -R port`)** - Reverse SOCKS proxy (OpenSSH 7.6+)

This tool is particularly useful for **penetration testers**, **red teamers**, **system administrators**, **security researchers**, or anyone needing to securely access services behind firewalls.

---

## ✨ Features

### Core Features
* **Local IP Detection:** Automatically identifies your local IP address for tunnel configuration
* **OS Compatibility Check:** Detects the operating system (Linux, Windows, macOS) to tailor `nmap` installation commands
* **Automated Nmap Installation:** Checks for `nmap` and installs it if missing, using appropriate package managers
* **Comprehensive Service Scanning:** Multiple scan types (quick, full, service, stealth, UDP, intense) to identify all open ports and services
* **Scan History:** Track all past scans with status, type, and service counts

### SSH Tunneling Features
* **Static SSH Tunneling (`-L`):** Local port forwarding to forward specific ports to remote services
* **Dynamic SSH Tunneling (`-D`):** SOCKS proxy for dynamic routing of traffic through SSH server
* **Remote SSH Tunneling (`-R`):** Reverse port forwarding when you can SSH out but firewall blocks inbound
* **Remote Dynamic Tunneling (`-R port`):** Reverse SOCKS proxy for flexible reverse access (OpenSSH 7.6+)
* **Tunnel Management:** Create, list, stop, and monitor multiple simultaneous tunnels
* **Tunnel Health Monitoring:** Real-time health checks, logs, and metrics

### Web Interface Features
* **Modern Red/Black Theme:** Hacking-inspired dark UI with red/black color scheme
* **Real-time Updates:** WebSocket support for live tunnel status monitoring
* **Tunnel Logs & Metrics:** Track tunnel activity, uptime, and health status
* **Proxychains Configuration Generator:** Built-in tool to generate proxychains configs for SOCKS proxies
* **Interactive Service Discovery:** Click-to-use discovered services for tunnel creation

### Technical Features
* **Cross-platform Support:** Works on Windows, Linux, and macOS
* **Docker Support:** Full Docker and Docker Compose support with `uv` package management
* **Modern Package Management:** Uses `uv` for fast, reliable dependency management
* **Thread-safe Operations:** Optimized tunnel management with proper locking

---

## 📋 Prerequisites

Before running MudaleTunnel, ensure you have:

* **Python 3.9+:** The script requires Python 3.9 or above (for `uv` compatibility)
* **Internet Connection:** Required for installing `nmap` and Python dependencies
* **SSH Client:** Your system should have an SSH client installed (usually pre-installed on Linux/macOS, available via Git Bash or PuTTY on Windows)
* **Nmap:** Will be automatically installed if missing (requires admin/sudo privileges)
* **Docker (Optional):** For containerized deployment

---

## 🚀 Installation

### Method 1: Direct Installation with `uv` (Recommended)

1. **Install `uv` (if not already installed):**
   ```bash
   # Linux/macOS
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Windows (PowerShell)
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. **Clone the repository:**
   ```bash
   git clone https://github.com/TarzEH/MudaleTunnel.git
   cd MudaleTunnel
   ```

3. **Install dependencies using `uv`:**
   ```bash
   uv sync
   ```

4. **Run MudaleTunnel:**
   ```bash
   uv run python main.py
   ```

### Method 2: Direct Installation with `pip`

1. **Clone the repository:**
   ```bash
   git clone https://github.com/TarzEH/MudaleTunnel.git
   cd MudaleTunnel
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run MudaleTunnel:**
   ```bash
   python main.py
   ```

   *Note: The script will attempt to install `nmap` automatically if it's not found on your system.*

### Method 3: Docker Installation (Recommended for Production)

**Using Docker Compose:**
```bash
docker-compose up -d
```

Access the web interface at `http://localhost:8000`

**Using Docker directly:**
```bash
docker build -t mudaletunnel .
docker run -d -p 8000:8000 mudaletunnel
```

See [README_DOCKER.md](README_DOCKER.md) for detailed Docker instructions.

---

## 🎮 Quick Start

### CLI Mode
```bash
# Using uv
uv run python main.py
# or
uv run python main.py cli

# Using pip
python main.py
# or
python main.py cli
```

### Web Interface Mode
```bash
# Using uv
uv run python main.py web

# Using pip
python main.py web
```

Then open `http://localhost:8000` in your browser.

---

## 📖 Command-Line Arguments

### Main Commands

```bash
python main.py [COMMAND] [OPTIONS]
```

**Available Commands:**

| Command | Description |
|---------|-------------|
| `cli` | Run in CLI mode (interactive) |
| `web` | Run in web interface mode |
| `static` | Create a static tunnel directly |
| `dynamic` | Create a dynamic tunnel directly |
| `remote` | Create a remote tunnel directly |
| `remote-dynamic` | Create a remote dynamic tunnel directly |
| *(none)* | Defaults to CLI mode if no command specified |

### Web Interface Options

```bash
python main.py web [OPTIONS]
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--port` | `-p` | Port for web server | `8000` |
| `--host` | `-h` | Host for web server | `127.0.0.1` |

### Static Tunnel Command

```bash
python main.py static --user USER --host HOST --target TARGET --port PORT [OPTIONS]
```

| Option | Short | Description | Required |
|--------|-------|-------------|----------|
| `--user` | `-u` | SSH username | Yes |
| `--host` | `-h` | SSH host | Yes |
| `--target` | `-t` | Target host | Yes |
| `--port` | `-p` | Remote port | Yes |
| `--local-port` | `-l` | Local port (default: same as remote) | No |
| `--execute/--no-execute` | | Execute tunnel automatically | Default: True |

**Example:**
```bash
python main.py static --user admin --host jumpbox.example.com --target 192.168.1.100 --port 80 --local-port 8080
```

### Dynamic Tunnel Command

```bash
python main.py dynamic --user USER --host HOST [OPTIONS]
```

| Option | Short | Description | Required |
|--------|-------|-------------|----------|
| `--user` | `-u` | SSH username | Yes |
| `--host` | `-h` | SSH host | Yes |
| `--port` | `-p` | Local SOCKS port (default: auto) | No |
| `--execute/--no-execute` | | Execute tunnel automatically | Default: True |

**Example:**
```bash
python main.py dynamic --user admin --host jumpbox.example.com --port 1080
```

### Remote Tunnel Command

```bash
python main.py remote --user USER --host HOST --bind-port PORT --target TARGET --target-port PORT [OPTIONS]
```

| Option | Short | Description | Required |
|--------|-------|-------------|----------|
| `--user` | `-u` | SSH username (on attacker machine) | Yes |
| `--host` | `-h` | SSH host (attacker IP) | Yes |
| `--bind-port` | `-b` | Remote bind port (on attacker machine) | Yes |
| `--target` | `-t` | Target host (internal service) | Yes |
| `--target-port` | `-p` | Target port (internal service) | Yes |
| `--bind-addr` | `-a` | Bind address (default: 127.0.0.1) | No |
| `--execute/--no-execute` | | Execute tunnel automatically | Default: True |

**Example:**
```bash
python main.py remote --user kali --host 192.168.118.4 --bind-port 2345 --target 10.4.50.215 --target-port 5432
```

### Remote Dynamic Tunnel Command

```bash
python main.py remote-dynamic --user USER --host HOST --socks-port PORT [OPTIONS]
```

| Option | Short | Description | Required |
|--------|-------|-------------|----------|
| `--user` | `-u` | SSH username (on attacker machine) | Yes |
| `--host` | `-h` | SSH host (attacker IP) | Yes |
| `--socks-port` | `-p` | Remote SOCKS port (on attacker machine) | Yes |
| `--bind-addr` | `-a` | Bind address (default: 127.0.0.1) | No |
| `--execute/--no-execute` | | Execute tunnel automatically | Default: True |

**Example:**
```bash
python main.py remote-dynamic --user kali --host 192.168.118.4 --socks-port 9998
```

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

## 📚 Usage Guide

## CLI Mode Usage

### Starting CLI Mode

```bash
uv run python main.py
# or
uv run python main.py cli
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
      └─ Use when: You have SSH access and can bind ports
   2. Dynamic tunneling (SOCKS proxy - ssh -D)
      └─ Use when: You need flexible access to multiple services
   3. Remote tunneling (Reverse port forwarding - ssh -R)
      └─ Use when: You can SSH out but firewall blocks inbound
   4. Remote dynamic tunneling (Reverse SOCKS - ssh -R port)
      └─ Use when: You can SSH out and need flexible reverse access (OpenSSH 7.6+)
   5. Manage existing tunnels
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

#### 4. Dynamic Tunneling (SOCKS Proxy)

**Example: Creating a SOCKS proxy**

```
Select tunneling mode:
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

Proxychains Configuration:
  Add to /etc/proxychains4.conf: socks5 127.0.0.1 1080
  Usage: proxychains nmap -sT -Pn target
```

**What happened:**
- Created SOCKS proxy: `ssh -D 1080 admin@jumpbox.example.com -N -f`
- SOCKS proxy is active on port 1080
- All traffic through this proxy will be routed through the SSH server

#### 5. Remote Tunneling (Reverse Port Forwarding)

**Example: Creating a reverse tunnel**

```
Select tunneling mode:
Enter your choice: 3

Remote Tunneling (Reverse Port Forwarding)
Use case: When you can SSH out but firewall blocks inbound connections
Enter remote bind port (on attacker machine): 2345
Enter bind address (default 127.0.0.1): 127.0.0.1
Enter target host (internal service): 10.4.50.215
Enter target port (internal service): 5432
Execute tunnel automatically? (yes/no, default: no): yes

✓ Remote tunnel created successfully!
Tunnel ID: c3d4e5f6-a7b8-9012-cdef-123456789012
Remote bind: 127.0.0.1:2345 -> Target: 10.4.50.215:5432

Access the service on attacker machine:
  Connect to: 127.0.0.1:2345
```

**What happened:**
- Created reverse tunnel: `ssh -R 127.0.0.1:2345:10.4.50.215:5432 kali@192.168.118.4 -N -f`
- Listening port is bound on the attacker machine (SSH server)
- Access the internal service from attacker machine at `127.0.0.1:2345`

#### 6. Remote Dynamic Tunneling (Reverse SOCKS Proxy)

**Example: Creating a reverse SOCKS proxy**

```
Select tunneling mode:
Enter your choice: 4

Remote Dynamic Tunneling (Reverse SOCKS Proxy)
Use case: When you can SSH out and need flexible access (OpenSSH 7.6+)
Enter remote SOCKS port (on attacker machine): 9998
Enter bind address (default 127.0.0.1): 127.0.0.1
Execute tunnel automatically? (yes/no, default: no): yes

✓ Remote dynamic tunnel (SOCKS proxy) created successfully!
Tunnel ID: d4e5f6a7-b8c9-0123-def0-234567890123
SOCKS proxy on attacker machine: 127.0.0.1:9998

Proxychains Configuration:
  Add to /etc/proxychains4.conf: socks5 127.0.0.1 9998
  Usage: proxychains nmap -sT -Pn target
```

**What happened:**
- Created reverse SOCKS proxy: `ssh -R 9998 kali@192.168.118.4 -N -f`
- SOCKS proxy is bound on attacker machine at `127.0.0.1:9998`
- Use proxychains on attacker machine to route tools through this proxy

#### 7. Tunnel Management

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
┏━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━┓
┃ ID            ┃ Type   ┃ Local Port            ┃ Remote                ┃ Status  ┃ PID   ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━┩
│ a1b2c3d4      ┃ STATIC │ 8080                  │ 192.168.1.100:80     │ active  │ 12345 │
│ b2c3d4e5      ┃ DYNAMIC│ 1080                  │ SOCKS Proxy           │ active  │ 12346 │
│ c3d4e5f6      ┃ REMOTE │ 127.0.0.1:2345        │ 10.4.50.215:5432     │ active  │ 12347 │
│ d4e5f6a7      ┃ REMOTE │ 127.0.0.1:9998        │ Remote SOCKS Proxy    │ active  │ 12348 │
└───────────────┴────────┴───────────────────────┴───────────────────────┴─────────┴───────┘
```

---

## 🌐 Web Interface Usage

### Starting Web Interface

```bash
# Using uv
uv run python main.py web

# Using pip
python main.py web
```

Then open your browser at `http://localhost:8000` (or your custom port).

### Web Interface Features

#### 1. Target Scanning

**Step 1: Enter Target**
- In the "Target Scanning" section, enter an IP address or domain name
- Select scan type: Quick, Full, Service, Stealth, UDP, or Intense
- Example: `192.168.1.100` or `example.com`

**Step 2: Click Scan**
- Click the "Scan" button
- Progress bar appears showing scan status
- Status messages update in real-time

**Step 3: View Results**
- Discovered services appear in the "Discovered Services" section
- Each service shows: Port, Service name, State
- Click "Use for Tunnel" to pre-fill tunnel creation form
- View scan history in the "Scan History" section

#### 2. Creating Tunnels

The web interface supports all 4 tunnel types with dedicated tabs:

**Static Tunnel (`-L`):**
- Direct port forwarding
- Use when you have SSH access and can bind ports
- Fill in: SSH user, host, target host, remote port, local port

**Dynamic Tunnel (`-D`):**
- SOCKS proxy for flexible routing
- Use when you need access to multiple services
- Fill in: SSH user, host, local SOCKS port

**Remote Tunnel (`-R`):**
- Reverse port forwarding
- Use when firewall blocks inbound connections
- Fill in: SSH user (attacker), host (attacker IP), remote bind port, target host, target port

**Remote Dynamic Tunnel (`-R port`):**
- Reverse SOCKS proxy
- Use for flexible reverse access (OpenSSH 7.6+)
- Fill in: SSH user (attacker), host (attacker IP), remote SOCKS port

#### 3. Proxychains Configuration

**What is Proxychains?**
- Forces network traffic from tools (nmap, smbclient, etc.) to go through a SOCKS proxy
- Essential when using dynamic or remote dynamic tunnels
- Uses LD_PRELOAD to hook into network functions

**How to Use:**
1. Create a dynamic or remote dynamic tunnel
2. Go to "Proxychains Configuration" section
3. Enter proxy type (SOCKS5 recommended), host, and port
4. Select chain type (strict, dynamic, or random)
5. Click "Generate Proxychains Config"
6. Copy the configuration to `/etc/proxychains4.conf` (requires sudo)
7. Use with: `proxychains <command>`

**Example:**
```bash
# After generating config, use it:
proxychains nmap -sT -Pn 172.16.50.217
proxychains smbclient -L //172.16.50.217/ -U user
```

#### 4. Managing Tunnels

**Viewing Active Tunnels:**
- All active tunnels are displayed in the "Active Tunnels" section
- Real-time status updates via WebSocket
- Color-coded status indicators (red=active, gray=stopped)

**Tunnel Actions:**
1. **Details:** View full tunnel configuration and SSH command
2. **Logs:** View tunnel logs in real-time
3. **Metrics:** View tunnel metrics (uptime, status checks, etc.)
4. **Stop:** Stop the tunnel

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

## 💡 Feature Examples

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
5. Configure browser to use SOCKS5 proxy at `127.0.0.1:1080`

**Result:**
- All browser traffic routes through the SSH server

### Example 3: Reverse Tunnel Through Firewall

**Scenario:** You compromised a host but firewall blocks inbound connections. You can SSH out to your attacker machine.

**CLI Method:**
```bash
python main.py
# Select: 1. Scan target and create tunnel
# Enter SSH username: kali
# Enter SSH host: 192.168.118.4 (attacker IP)
# Select: 3. Remote tunneling
# Remote bind port: 2345
# Target host: 10.4.50.215
# Target port: 5432
# Execute: yes
```

**Web Method:**
1. Switch to "Remote (-R)" tab
2. Fill SSH credentials (attacker machine)
3. Enter remote bind port, target host, and target port
4. Click "Create Remote Tunnel"

**Result:**
- Access internal PostgreSQL database from attacker machine at `127.0.0.1:2345`

### Example 4: Reverse SOCKS Proxy for Enumeration

**Scenario:** You need flexible access to multiple internal services through a reverse tunnel.

**CLI Method:**
```bash
python main.py
# Select: 1. Scan target and create tunnel
# Enter SSH username: kali
# Enter SSH host: 192.168.118.4 (attacker IP)
# Select: 4. Remote dynamic tunneling
# Remote SOCKS port: 9998
# Execute: yes
```

**Web Method:**
1. Switch to "Remote Dynamic (-R)" tab
2. Fill SSH credentials (attacker machine)
3. Enter remote SOCKS port
4. Click "Create Remote Dynamic Tunnel"
5. Generate proxychains config in web UI
6. Use proxychains on attacker machine

**Result:**
- Use proxychains on attacker machine to route tools through reverse SOCKS proxy
- Example: `proxychains nmap -sT -Pn 172.16.50.217`

### Example 5: Multiple Port Forwards

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

---

## 🔧 Advanced Usage

### Running Multiple Instances

You can run both CLI and web interface simultaneously by using different terminals:

**Terminal 1 (Web):**
```bash
uv run python main.py web --port 8000
```

**Terminal 2 (CLI):**
```bash
uv run python main.py cli
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

MudaleTunnel generates standard SSH commands. To add custom options:

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

### Using Proxychains with Dynamic Tunnels

1. **Create a dynamic tunnel:**
   ```bash
   python main.py dynamic --user admin --host jumpbox.example.com --port 1080
   ```

2. **Configure proxychains:**
   - Use the web UI's Proxychains Configuration generator
   - Or manually edit `/etc/proxychains4.conf`:
     ```
     socks5 127.0.0.1 1080
     ```

3. **Use proxychains:**
   ```bash
   proxychains nmap -sT -Pn target
   proxychains smbclient -L //target/ -U user
   ```

---

## 🐳 Docker Usage

See [README_DOCKER.md](README_DOCKER.md) for comprehensive Docker documentation.

**Quick Start:**
```bash
docker-compose up -d
```

Access web interface at `http://localhost:8000`

---

## 🛠️ Troubleshooting

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

**Issue: "Remote tunnel not accessible"**
- **Solution:**
  - Ensure SSH server on attacker machine allows remote port forwarding
  - Check `GatewayPorts` setting in SSH server config
  - Verify firewall on attacker machine allows the port
  - Test connection from attacker machine: `curl http://127.0.0.1:PORT`

### Getting Help

- Check tunnel logs for detailed error messages
- Use tunnel health check feature
- Verify SSH connection works manually
- Review system logs for SSH errors

---

## 📝 Best Practices

1. **Use SSH Keys:** Set up SSH key authentication to avoid password prompts
2. **Monitor Tunnels:** Regularly check tunnel health, especially for long-running tunnels
3. **Clean Up:** Stop unused tunnels to free up ports
4. **Security:** Only create tunnels to trusted hosts
5. **Port Management:** Use consistent port numbering for easier management
6. **Logs:** Review tunnel logs if experiencing issues
7. **Proxychains:** Use proxychains for tools that don't natively support SOCKS proxies
8. **Network Mode:** Use host network mode in Docker for better tunnel accessibility (Linux only)

---

## 📦 Dependencies

### Core Dependencies
* `typer`: For building the command-line interface
* `rich`: For beautiful terminal output and progress bars
* `typing_extensions`: For advanced type hints

### Web Interface Dependencies
* `fastapi`: For web interface backend
* `uvicorn`: ASGI server for FastAPI
* `websockets`: For real-time WebSocket updates
* `jinja2`: For HTML templating

### Package Management
* `uv`: Modern Python package installer (recommended)
* `pip`: Traditional Python package installer (alternative)

See `requirements.txt` and `pyproject.toml` for complete list with versions.

---

## 🤝 Contributing

Contributions are welcome! If you have suggestions for improvements, new features, or bug fixes, please feel free to open an [issue](https://github.com/TarzEH/MudaleTunnel/issues) or submit a [pull request](https://github.com/TarzEH/MudaleTunnel/pulls).

---

## 📄 License

This project is open-source and available under the [MIT License](https://opensource.org/licenses/MIT).

---

## 🙏 Acknowledgments

Built with ❤️ for the security and sysadmin community.

Special thanks to the open-source community for the amazing tools that make this possible.
