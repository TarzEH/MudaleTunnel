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


class MudaleTunnelUI:

    def __init__(self):
        
        self.myip = [
            (s.connect(("8.8.8.8", 53)), s.getsockname()[0], s.close())
            for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]
        ][0][1]
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
        try:
            subprocess.run(["choco", "-v"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("[green]Chocolatey is already installed.[/green]")
            return True
        except FileNotFoundError:
            print("[red]Chocolatey is not installed.[/red]")
            return False

    def install_chocolatey(self):
        approval = input("Chocolatey is required to install nmap. Would you like to install Chocolatey? (y/n): ").lower()
        if approval == 'y':
            install_command = '''Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.WebClient]::new().DownloadString('https://community.chocolatey.org/install.ps1') | Invoke-Expression'''
            subprocess.run(["powershell", "-Command", install_command], check=True)
            print("[green]Chocolatey installed successfully.[/green]")
        else:
            print("[yellow]Installation canceled by user.[/yellow]")
            return False
        return True

    def check_homebrew_installed(self):
        try:
            subprocess.run(["brew", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("[green]Homebrew is already installed.[/green]")
            return True
        except FileNotFoundError:
            print("[red]Homebrew is not installed.[/red]")
            return False

    def install_homebrew(self):
        approval = input("Homebrew is required to install nmap. Would you like to install Homebrew? (y/n): ").lower()
        if approval == 'y':
            install_command = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
            subprocess.run(["/bin/bash", "-c", install_command], check=True)
            print("[green]Homebrew installed successfully.[/green]")
        else:
            print("[yellow]Installation canceled by user.[/yellow]")
            return False
        return True

    def install_nmap(self, os_type):
        approval = input("nmap is not installed. Would you like to download and install it? (y/n): ").lower()
        if approval == 'y':
            if os_type == "Linux":
                distro = platform.linux_distribution()[0]
                if 'Ubuntu' in distro or 'Debian' in distro:
                    subprocess.run(["sudo", "apt-get", "install", "nmap", "-y"])
                elif 'CentOS' in distro or 'RedHat' in distro:
                    subprocess.run(["sudo", "yum", "install", "nmap", "-y"])
                print("[green]nmap installed successfully.[/green]")
            elif os_type == "Windows":
                if not self.check_chocolatey_installed():
                    if not self.install_chocolatey():
                        return  # Exit if user cancels Chocolatey installation
                subprocess.run(["choco", "install", "nmap", "-y"], check=True)
                print("[green]nmap installed successfully on Windows via Chocolatey.[/green]")
            elif os_type == "Darwin":
                if not self.check_homebrew_installed():
                    if not self.install_homebrew():
                        return  # Exit if user cancels Homebrew installation
                subprocess.run(["brew", "install", "nmap"], check=True)
                print("[green]nmap installed successfully on macOS via Homebrew.[/green]")
        else:
            print("[yellow]Installation canceled by user.[/yellow]")

    def scan_nmap_services(self, target: str):
        # Perform the nmap scan
        print(f"Starting nmap scan on {target}...")
        try:
            result = subprocess.run(["nmap", "-sV", target], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            output = result.stdout
            if "open" in output:
                print("[green]Scan completed! Listing open services:[/green]")
                self.display_open_services(output)
            else:
                print("[yellow]No open services found on the target.[/yellow]")
        except Exception as e:
            print(f"[red]Error running nmap scan: {e}[/red]")

    def display_open_services(self, nmap_output: str):
        # Parse and display open services
        table = Table(title="Open Ports and Services")
        table.add_column("Port", justify="right", style="cyan", no_wrap=True)
        table.add_column("State", justify="center", style="green")
        table.add_column("Service", justify="left", style="magenta")

        for line in nmap_output.splitlines():
            if "open" in line:
                parts = line.split()
                port = parts[0]
                state = parts[1]
                service = parts[2]
                table.add_row(port, state, service)

        print(table)

    def cli_menu(self):
        os_type = self.check_os()
        if not self.check_nmap_installed():
            self.install_nmap(os_type)

        # Prompt for target and run nmap scan
        target = input("Enter the target IP or domain to scan: ")
        self.scan_nmap_services(target)

    def spinnersquare(self, descriptiontask: str, delay: float = 5, final_message: str = "Done!"):
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=False,
        ) as progress:
            progress.add_task(description=f"{descriptiontask}...", total=None)
            time.sleep(delay)
        print(f"{final_message}")
