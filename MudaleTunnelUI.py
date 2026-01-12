import socket
import time
import typer
import platform
import subprocess
import os
import urllib.request
from typing_extensions import Annotated
from rich import print
from rich.progress import Progress, SpinnerColumn, TextColumn, track
from rich.table import Table
from tunnel_manager import TunnelManager


class MudaleTunnelUI:

    def __init__(self, tunnel_manager: TunnelManager = None):
        self.tunnel_manager = tunnel_manager or TunnelManager()
        self.myip = self.tunnel_manager.myip
        self.logo = r"""   
        ▄▄       ▄▄  ▄         ▄  ▄▄▄▄▄▄▄▄▄▄   ▄▄▄▄▄▄▄▄▄▄▄  ▄            ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄         ▄  ▄▄        ▄  ▄▄        ▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄                
        ▐░░▌     ▐░░▌▐░▌       ▐░▌▐░░░░░░░░░░▌ ▐░░░░░░░░░░░▌▐░▌          ▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░▌       ▐░▌▐░░▌      ▐░▌▐░░▌      ▐░▌▐░░░░░░░░░░░▌▐░▌               
        ▐░▌░▌   ▐░▐░▌▐░▌       ▐░▌▐░█▀▀▀▀▀▀▀█░▌▐░█▀▀▀▀▀▀▀█░▌▐░▌          ▐░█▀▀▀▀▀▀▀▀▀  ▀▀▀▀█░█▀▀▀▀ ▐░▌       ▐░▌▐░▌░▌     ▐░▌▐░▌░▌     ▐░▌▐░█▀▀▀▀▀▀▀▀▀ ▐░▌               
        ▐░▌▐░▌ ▐░▌▐░▌▐░▌       ▐░▌▐░▌       ▐░▌▐░▌       ▐░▌▐░▌          ▐░▌               ▐░▌     ▐░▌       ▐░▌▐░▌▐░▌    ▐░▌▐░▌▐░▌    ▐░▌▐░▌          ▐░▌               
        ▐░▌ ▐░▐░▌ ▐░▌▐░▌       ▐░▌▐░▌       ▐░▌▐░█▄▄▄▄▄▄▄█░▌▐░▌          ▐░█▄▄▄▄▄▄▄▄▄      ▐░▌     ▐░▌       ▐░▌▐░▌ ▐░▌   ▐░▌▐░▌ ▐░▌   ▐░▌▐░█▄▄▄▄▄▄▄▄▄ ▐░▌               
        ▐░▌  ▐░▌  ▐░▌▐░▌       ▐░▌▐░▌       ▐░▌▐░░░░░░░░░░░▌▐░▌          ▐░░░░░░░░░░░▌     ▐░▌     ▐░▌       ▐░▌▐░▌  ▐░▌  ▐░▌▐░▌  ▐░▌  ▐░▌▐░░░░░░░░░░░▌▐░▌               
        ▐░▌   ▀   ▐░▌▐░▌       ▐░▌▐░▌       ▐░▌▐░█▀▀▀▀▀▀▀█░▌▐░▌          ▐░█▀▀▀▀▀▀▀▀▀      ▐░▌     ▐░▌       ▐░▌▐░▌   ▐░▌ ▐░▌▐░▌   ▐░▌ ▐░▌▐░█▀▀▀▀▀▀▀▀▀ ▐░▌               
        ▐░▌       ▐░▌▐░▌       ▐░▌▐░▌       ▐░▌▐░▌       ▐░▌▐░▌          ▐░▌               ▐░▌     ▐░▌       ▐░▌▐░▌    ▐░▌▐░▌▐░▌    ▐░▌▐░▌▐░▌          ▐░▌               
        ▐░▌       ▐░▌▐░█▄▄▄▄▄▄▄█░▌▐░█▄▄▄▄▄▄▄█░▌▐░▌       ▐░▌▐░█▄▄▄▄▄▄▄▄▄ ▐░█▄▄▄▄▄▄▄▄▄      ▐░▌     ▐░█▄▄▄▄▄▄▄█░▌▐░▌     ▐░▐░▌▐░▌     ▐░▐░▌▐░█▄▄▄▄▄▄▄▄▄ ▐░█▄▄▄▄▄▄▄▄▄      
        ▐░▌       ▐░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░▌ ▐░▌       ▐░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌     ▐░▌     ▐░░░░░░░░░░░▌▐░▌      ▐░░▌▐░▌      ▐░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌     
        ▀         ▀  ▀▀▀▀▀▀▀▀▀▀▀  ▀▀▀▀▀▀▀▀▀▀   ▀         ▀  ▀▀▀▀▀▀▀▀▀▀▀  ▀▀▀▀▀▀▀▀▀▀▀       ▀       ▀▀▀▀▀▀▀▀▀▀▀  ▀        ▀▀  ▀        ▀▀  ▀▀▀▀▀▀▀▀▀▀▀  ▀▀▀▀▀▀▀▀▀▀▀      
        """
        print(f"[bold blue]{self.logo}")
        print(f"[bold red]{self.myip}")

    def check_os(self):
        os_type = platform.system()
        print(f"Operating System: {os_type}")
        return os_type

    def check_nmap_installed(self):
        try:
            subprocess.run(["nmap", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("[green]nmap is already installed.[/green]")
            return True
        except FileNotFoundError:
            print("[red]nmap is not installed.[/red]")
            return False

    def check_chocolatey_installed(self):
        """Check if Chocolatey is installed on Windows."""
        try:
            subprocess.run(["choco", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False
    
    def install_chocolatey(self):
        """Install Chocolatey on Windows."""
        print("[yellow]Chocolatey is not installed. Installing Chocolatey...[/yellow]")
        try:
            # PowerShell command to install Chocolatey
            ps_cmd = "Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
            subprocess.run(["powershell", "-Command", ps_cmd], check=True)
            print("[green]Chocolatey installed successfully.[/green]")
        except Exception as e:
            print(f"[red]Failed to install Chocolatey: {e}[/red]")
            raise
    
    def check_homebrew_installed(self):
        """Check if Homebrew is installed on macOS."""
        try:
            subprocess.run(["brew", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False
    
    def install_homebrew(self):
        """Install Homebrew on macOS."""
        print("[yellow]Homebrew is not installed. Installing Homebrew...[/yellow]")
        try:
            install_cmd = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
            subprocess.run(install_cmd, shell=True, check=True)
            print("[green]Homebrew installed successfully.[/green]")
        except Exception as e:
            print(f"[red]Failed to install Homebrew: {e}[/red]")
            raise
    
    def install_nmap(self, os_type):
        if os_type == "Linux":
            try:
                subprocess.run(["sudo", "apt-get", "install", "nmap", "-y"], check=True)
            except Exception:
                subprocess.run(["sudo", "yum", "install", "nmap", "-y"], check=True)
        elif os_type == "Windows":
            if not self.check_chocolatey_installed():
                self.install_chocolatey()
            subprocess.run(["choco", "install", "nmap", "-y"], check=True)
        elif os_type == "Darwin":
            if not self.check_homebrew_installed():
                self.install_homebrew()
            subprocess.run(["brew", "install", "nmap"], check=True)

    def scan_nmap_services(self, target: str):
        print(f"Starting full nmap scan on {target}...")
        result = subprocess.run(["nmap", "-p-", "-sV", target], stdout=subprocess.PIPE, text=True)
        output = result.stdout
        self.display_open_services(output)
        self.interactive_shell(output)

    def display_open_services(self, nmap_output: str):
        table = Table(title="Open Ports and Services")
        table.add_column("Port", style="cyan")
        table.add_column("State", style="green")
        table.add_column("Service", style="magenta")

        for line in nmap_output.splitlines():
            if "open" in line:
                parts = line.split()
                port, state, service = parts[0], parts[1], parts[2]
                table.add_row(port, state, service)
        print(table)

    def choose_tunnel_mode(self):
        """Present menu to choose between static and dynamic tunneling."""
        print("\n[bold cyan]Select tunneling mode:[/bold cyan]")
        print("1. Static tunneling (Local port forwarding - ssh -L)")
        print("2. Dynamic tunneling (SOCKS proxy - ssh -D)")
        print("3. Manage existing tunnels")
        print("0. Exit")
        
        while True:
            try:
                choice = int(input("\nEnter your choice: "))
                if choice == 0:
                    return None
                elif choice == 1:
                    return "static"
                elif choice == 2:
                    return "dynamic"
                elif choice == 3:
                    self.manage_tunnels_menu()
                    return self.choose_tunnel_mode()
                else:
                    print("[red]Invalid selection. Please choose 0-3.[/red]")
            except ValueError:
                print("[red]Invalid input. Please enter a number.[/red]")
    
    def create_static_tunnel(self, ssh_user: str, ssh_host: str, target_host: str, remote_port: int, local_port: int = None, execute: bool = True):
        """Create a static tunnel using TunnelManager."""
        try:
            tunnel_id, ssh_command = self.tunnel_manager.create_static_tunnel(
                ssh_user, ssh_host, target_host, remote_port, local_port, execute
            )
            if execute:
                print(f"[green]✓ Static tunnel created successfully![/green]")
                print(f"[cyan]Tunnel ID: {tunnel_id}[/cyan]")
                print(f"[cyan]Local port: {local_port} -> Remote: {target_host}:{remote_port}[/cyan]")
            else:
                print(f"[yellow]SSH Command (not executed):[/yellow]")
                print(f"[cyan]{ssh_command}[/cyan]")
            return tunnel_id, ssh_command
        except ValueError as e:
            print(f"[red]Error: {e}[/red]")
            return None, None
        except Exception as e:
            print(f"[red]Failed to create tunnel: {e}[/red]")
            return None, None
    
    def create_dynamic_tunnel(self, ssh_user: str, ssh_host: str, local_port: int = None, execute: bool = True):
        """Create a dynamic tunnel using TunnelManager."""
        try:
            tunnel_id, ssh_command = self.tunnel_manager.create_dynamic_tunnel(
                ssh_user, ssh_host, local_port, execute
            )
            if execute:
                print(f"[green]✓ Dynamic tunnel (SOCKS proxy) created successfully![/green]")
                print(f"[cyan]Tunnel ID: {tunnel_id}[/cyan]")
                print(f"[cyan]SOCKS proxy listening on port: {local_port}[/cyan]")
                print("\n[yellow]To use the SOCKS proxy:[/yellow]")
                print(f"  - Firefox: Settings > Network Settings > Manual proxy > SOCKS Host: 127.0.0.1, Port: {local_port}")
                print(f"  - curl: curl --socks5 127.0.0.1:{local_port} http://example.com")
                print(f"  - Environment: export HTTP_PROXY=socks5://127.0.0.1:{local_port}")
            else:
                print(f"[yellow]SSH Command (not executed):[/yellow]")
                print(f"[cyan]{ssh_command}[/cyan]")
            return tunnel_id, ssh_command
        except ValueError as e:
            print(f"[red]Error: {e}[/red]")
            return None, None
        except Exception as e:
            print(f"[red]Failed to create tunnel: {e}[/red]")
            return None, None
    
    def list_active_tunnels(self):
        """Display all active tunnels in a table."""
        tunnels = self.tunnel_manager.list_tunnels()
        
        if not tunnels:
            print("[yellow]No active tunnels.[/yellow]")
            return
        
        table = Table(title="Active Tunnels")
        table.add_column("ID", style="cyan", max_width=8)
        table.add_column("Type", style="magenta")
        table.add_column("Local Port", style="green")
        table.add_column("Remote", style="yellow")
        table.add_column("Status", style="bold")
        table.add_column("PID", style="dim")
        
        for tunnel in tunnels:
            tunnel_id = tunnel.get("id", "N/A")[:8]
            tunnel_type = tunnel.get("type", "N/A")
            local_port = str(tunnel.get("local_port", "N/A"))
            status = tunnel.get("status", "unknown")
            
            if tunnel_type == "static":
                remote = f"{tunnel.get('remote_host', 'N/A')}:{tunnel.get('remote_port', 'N/A')}"
            else:
                remote = "SOCKS Proxy"
            
            pid = str(tunnel.get("pid", "N/A"))
            
            status_color = "green" if status == "active" else "red"
            table.add_row(
                tunnel_id,
                tunnel_type.upper(),
                local_port,
                remote,
                f"[{status_color}]{status}[/{status_color}]",
                pid
            )
        
        print(table)
    
    def stop_tunnel(self, tunnel_id: str):
        """Stop a specific tunnel."""
        if self.tunnel_manager.stop_tunnel(tunnel_id):
            print(f"[green]✓ Tunnel {tunnel_id[:8]} stopped successfully.[/green]")
        else:
            print(f"[red]Failed to stop tunnel {tunnel_id[:8]}.[/red]")
    
    def stop_all_tunnels(self):
        """Stop all active tunnels."""
        count = self.tunnel_manager.stop_all_tunnels()
        print(f"[green]✓ Stopped {count} tunnel(s).[/green]")
    
    def manage_tunnels_menu(self):
        """Menu for managing tunnels."""
        while True:
            print("\n[bold cyan]Tunnel Management:[/bold cyan]")
            print("1. List all tunnels")
            print("2. Stop a tunnel")
            print("3. Stop all tunnels")
            print("4. Check tunnel health")
            print("0. Back")
            
            try:
                choice = int(input("\nEnter your choice: "))
                if choice == 0:
                    break
                elif choice == 1:
                    self.list_active_tunnels()
                elif choice == 2:
                    self.list_active_tunnels()
                    tunnel_id = input("Enter tunnel ID to stop: ").strip()
                    if tunnel_id:
                        self.stop_tunnel(tunnel_id)
                elif choice == 3:
                    confirm = input("Are you sure you want to stop all tunnels? (yes/no): ")
                    if confirm.lower() == "yes":
                        self.stop_all_tunnels()
                elif choice == 4:
                    self.list_active_tunnels()
                    tunnel_id = input("Enter tunnel ID to check: ").strip()
                    if tunnel_id:
                        health = self.tunnel_manager.check_tunnel_health(tunnel_id)
                        print(f"\n[cyan]Tunnel Health:[/cyan]")
                        print(f"  Healthy: {health.get('healthy', False)}")
                        print(f"  Process Running: {health.get('process_running', False)}")
                        print(f"  Port Listening: {health.get('port_listening', False)}")
                        if health.get('reason'):
                            print(f"  Reason: {health.get('reason')}")
                else:
                    print("[red]Invalid selection.[/red]")
            except ValueError:
                print("[red]Invalid input. Please enter a number.[/red]")
    
    def interactive_shell(self, nmap_output: str):
        """Enhanced interactive shell with static/dynamic tunneling support."""
        services = []
        for line in nmap_output.splitlines():
            if "open" in line:
                parts = line.split()
                if len(parts) >= 3:
                    port, state, service = parts[0], parts[1], parts[2]
                    services.append((port, service))

        if not services:
            print("[yellow]No open services found.[/yellow]")
            return

        ssh_user = input("\nEnter the SSH username: ")
        ssh_host = input("Enter the SSH hostname or IP address: ")

        while True:
            mode = self.choose_tunnel_mode()
            if mode is None:
                break
            
            if mode == "static":
                # Static tunneling
                print("\n[bold cyan]Available services for static tunneling:[/bold cyan]")
                for idx, (port, service) in enumerate(services, start=1):
                    print(f"{idx}. Port: {port}, Service: {service}")
                
                try:
                    choice = int(input("\nSelect a service number (0 to cancel): "))
                    if choice == 0:
                        continue
                    elif 1 <= choice <= len(services):
                        port_str, service = services[choice - 1]
                        remote_port = self.tunnel_manager._parse_port(port_str)
                        
                        print(f"\nSelected Service: {service} on Port: {port_str}")
                        local_port_input = input(f"Enter local port (default {remote_port}): ").strip()
                        local_port = int(local_port_input) if local_port_input.isdigit() else remote_port
                        
                        execute_choice = input("Execute tunnel automatically? (yes/no, default: no): ").strip().lower()
                        execute = execute_choice == "yes"
                        
                        self.create_static_tunnel(
                            ssh_user, ssh_host, self.myip, remote_port, local_port, execute
                        )
                    else:
                        print("[red]Invalid selection.[/red]")
                except ValueError:
                    print("[red]Invalid input.[/red]")
            
            elif mode == "dynamic":
                # Dynamic tunneling
                print("\n[bold cyan]Dynamic Tunneling (SOCKS Proxy)[/bold cyan]")
                local_port_input = input("Enter local SOCKS port (default: auto): ").strip()
                local_port = int(local_port_input) if local_port_input.isdigit() else None
                
                execute_choice = input("Execute tunnel automatically? (yes/no, default: no): ").strip().lower()
                execute = execute_choice == "yes"
                
                self.create_dynamic_tunnel(ssh_user, ssh_host, local_port, execute)

    def run_with_args(self, target, username=None, ssh_host=None, port=None, local_port=None):
        """Run with command line arguments instead of interactive mode."""
        os_type = self.check_os()
        if not self.check_nmap_installed():
            self.install_nmap(os_type)
        
        print(f"Starting full nmap scan on {target}...")
        result = subprocess.run(["nmap", "-p-", "-sV", target], stdout=subprocess.PIPE, text=True)
        output = result.stdout
        self.display_open_services(output)
        
        if username and ssh_host:
            services = []
            for line in output.splitlines():
                if "open" in line:
                    parts = line.split()
                    port_info, service = parts[0], parts[2]
                    services.append((port_info, service))
            
            if port:
                # Find specific port
                target_service = None
                for p, s in services:
                    if str(port) in p:
                        target_service = (p, s)
                        break
                
                if target_service:
                    port_info, service = target_service
                    final_local_port = local_port or port
                    ssh_command = f"ssh -L {final_local_port}:{self.myip}:{port_info} {username}@{ssh_host}"
                    print(f"\nSSH Tunnel Command:\n{ssh_command}")
                else:
                    print(f"[red]Port {port} not found in scan results[/red]")
            else:
                print("\n[yellow]Use --port to specify which service to tunnel[/yellow]")
        else:
            print("\n[yellow]Use --user and --ssh-host to generate tunnel command[/yellow]")

    def cli_menu(self):
        os_type = self.check_os()
        if not self.check_nmap_installed():
            try:
                self.install_nmap(os_type)
            except Exception as e:
                print(f"[red]Failed to install nmap: {e}[/red]")
                print("[yellow]Please install nmap manually and try again.[/yellow]")
                return
        
        while True:
            print("\n[bold cyan]MudaleTunnel Main Menu:[/bold cyan]")
            print("1. Scan target and create tunnel")
            print("2. Manage existing tunnels")
            print("0. Exit")
            
            try:
                choice = int(input("\nEnter your choice: "))
                if choice == 0:
                    print("[yellow]Exiting...[/yellow]")
                    # Stop all tunnels on exit
                    tunnels = self.tunnel_manager.list_tunnels()
                    if tunnels:
                        confirm = input(f"\nYou have {len(tunnels)} active tunnel(s). Stop all? (yes/no): ")
                        if confirm.lower() == "yes":
                            self.stop_all_tunnels()
                    break
                elif choice == 1:
                    target = input("Enter the target IP or domain to scan: ")
                    self.scan_nmap_services(target)
                elif choice == 2:
                    self.manage_tunnels_menu()
                else:
                    print("[red]Invalid selection.[/red]")
            except ValueError:
                print("[red]Invalid input. Please enter a number.[/red]")
            except KeyboardInterrupt:
                print("\n[yellow]Interrupted. Stopping all tunnels...[/yellow]")
                self.stop_all_tunnels()
                break
