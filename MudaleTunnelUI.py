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

    def interactive_shell(self, nmap_output: str):
        services = []
        for line in nmap_output.splitlines():
            if "open" in line:
                parts = line.split()
                port, service = parts[0], parts[2]
                services.append((port, service))

        ssh_user = input("Enter the SSH username: ")
        ssh_host = input("Enter the SSH hostname or IP address: ")

        while True:
            print("\nAvailable services for tunneling:")
            for idx, (port, service) in enumerate(services, start=1):
                print(f"{idx}. Port: {port}, Service: {service}")
            
            try:
                choice = int(input("Select a service number for SSH tunneling or type 0 to exit: "))
                if choice == 0:
                    print("Exiting interactive shell.")
                    break
                elif 1 <= choice <= len(services):
                    port, service = services[choice - 1]
                    print(f"Selected Service: {service} on Port: {port}")
                    
                    # Prompt for local port
                    local_port = input(f"Enter a local port to use for tunneling (default is {port}): ")
                    if not local_port.isdigit():
                        print("[red]Invalid input for local port. Using remote port as default.[/red]")
                        local_port = port
                    
                    # SSH tunneling command
                    ssh_command = f"ssh -L {local_port}:{self.myip}:{port} {ssh_user}@{ssh_host}"
                    print(f"Use the following command to tunnel over SSH:\n{ssh_command}")
                else:
                    print("[red]Invalid selection. Please choose a valid number.[/red]")
            except ValueError:
                print("[red]Invalid input. Please enter a number.[/red]")

    def cli_menu(self):
        os_type = self.check_os()
        if not self.check_nmap_installed():
            self.install_nmap(os_type)
        target = input("Enter the target IP or domain to scan: ")
        self.scan_nmap_services(target)
