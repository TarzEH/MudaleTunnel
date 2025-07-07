# MudaleTunnel
![image](https://github.com/user-attachments/assets/69ab63fd-533d-4fb9-b704-1be00d4f6001)


## Description

MudaleTunnel is a **command-line interface (CLI) tool** designed to simplify the process of setting up **SSH tunnels** to exposed services on a target machine. It automates the detection of open ports and services using **`nmap`**, and then provides an interactive interface to generate the appropriate **`ssh -L` command** for port forwarding. This tool is particularly useful for penetration testers, system administrators, or anyone needing to securely access services behind a firewall.

-----

## Features

  * **Local IP Detection:** Automatically identifies your local IP address for tunnel configuration.
  * **OS Compatibility Check:** Detects the operating system (Linux, Windows, macOS) to tailor `nmap` installation commands.
  * **Automated Nmap Installation:** Checks for `nmap` and installs it if missing, using appropriate package managers (`apt`/`yum` for Linux, Chocolatey for Windows, Homebrew for macOS).
  * **Comprehensive Service Scanning:** Performs a full `nmap` scan (`-p- -sV`) on the target to identify all open ports and their associated services.
  * **Rich Output Display:** Presents open services in a clear, readable table format using the `rich` library.
  * **Interactive Tunneling Shell:** Allows users to select a discovered service and specify a local port to dynamically generate the SSH tunneling command.
  * **User-Friendly Interface:** Built with `typer` and `rich` for an intuitive and visually appealing command-line experience.

-----

## How It Works

MudaleTunnel streamlines the SSH tunneling process by:

1.  **Identifying Your Local IP:** It first determines your machine's IP address, which is crucial for constructing the SSH tunnel command.
2.  **Nmap Integration:**
      * It checks for the presence of `nmap` on your system.
      * If `nmap` is not found, it attempts to install it using the default package manager for your detected operating system (e.g., `apt`, `yum`, `choco`, `brew`).
      * Once `nmap` is available, it executes a comprehensive port scan (`nmap -p- -sV`) against the target IP or domain you provide. This scan identifies all open ports and the services running on them.
3.  **Interactive Tunnel Setup:**
      * The scan results are presented in a clear, tabular format.
      * You are then prompted to enter an SSH username and the remote host's IP address or hostname.
      * An interactive menu displays the discovered open services. You can select a service by its corresponding number.
      * For the chosen service, you can specify a local port on your machine to forward the traffic. If no local port is specified, the remote service's port is used by default.
4.  **SSH Command Generation:** Based on your selections, MudaleTunnel constructs and displays the complete `ssh -L` command, which you can then copy and paste into your terminal to establish the port forward. This command typically looks like: `ssh -L [local_port]:[your_local_ip]:[remote_service_port] [ssh_user]@[ssh_host]`.

-----

## Prerequisites

Before running MudaleTunnel, ensure you have the following:

  * **Python 3.x:** The script is written and tested with Python 3.
  * **Internet Connection:** Required for installing `nmap` and Python dependencies.
  * **SSH Client:** Your system should have an SSH client installed (usually pre-installed on Linux/macOS, available via Git Bash or PuTTY on Windows).

-----

## Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/TarzEH/MudaleTunnel.git
    cd MudaleTunnel
    ```

2.  **Install Python dependencies:**

    ```bash
    pip install typer rich typing_extensions
    ```

    *Note: The script will attempt to install `nmap` automatically if it's not found on your system.*

-----

## Usage

To run MudaleTunnel, execute the Python script from your terminal:

```bash
python main.py
```

The tool will guide you through the following steps:

1.  **Display Logo and Local IP:** It will first show the MudaleTunnel logo and your local IP address.

2.  **OS Check and Nmap Installation:** It will check your operating system and ensure `nmap` is installed. If not, it will prompt for installation (requires `sudo` on Linux/macOS, or administrator privileges on Windows for Chocolatey).

3.  **Enter Target:** You will be prompted to enter the target IP address or domain name to scan:

    ```
    Enter the target IP or domain to scan: example.com
    ```

4.  **Nmap Scan and Service Display:** MudaleTunnel will perform a full `nmap` scan and display the open ports and services in a table.

5.  **Interactive Shell for Tunneling:** You will then enter an interactive shell where you can select a service to tunnel:

    ```
    Enter the SSH username: your_username
    Enter the SSH hostname or IP address: remote_host_ip

    Available services for tunneling:
    1. Port: 22/tcp, Service: ssh
    2. Port: 80/tcp, Service: http
    3. Port: 443/tcp, Service: https
    ...

    Select a service number for SSH tunneling or type 0 to exit: 1
    Selected Service: ssh on Port: 22/tcp
    Enter a local port to use for tunneling (default is 22/tcp): 8080
    Use the following command to tunnel over SSH:
    ssh -L 8080:192.168.1.100:22/tcp your_username@remote_host_ip
    ```

      * You will be asked for the SSH username and the remote SSH host/IP.
      * Choose a service by its number.
      * Optionally, specify a local port for the tunnel. If left blank, the remote port will be used as the local port.
      * The tool will then print the `ssh -L` command you can use to establish the tunnel.

-----

## Dependencies

  * `typer`: For building the command-line interface.
  * `rich`: For beautiful terminal output and progress bars.
  * `typing_extensions`: For advanced type hints.

-----

## Contributing

Contributions are welcome\! If you have suggestions for improvements, new features, or bug fixes, please feel free to open an [issue](https://www.google.com/search?q=https://github.com/TarzEH/MudaleTunnel/issues) or submit a [pull request](https://www.google.com/search?q=https://github.com/TarzEH/MudaleTunnel/pulls).

-----

## License

This project is open-source and available under the [MIT License](https://opensource.org/licenses/MIT).

-----
