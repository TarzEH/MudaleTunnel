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

class MudaleTunnelUI:

    def __init__(self):
        # Get the local IP address
        self.myip = [
            (s.connect(("8.8.8.8", 53)), s.getsockname()[0], s.close())
            for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]
        ][0][1]

        # Define the logo
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
        print(f"[bold red]Your IP Address: {self.myip}")

    def check_os(self):
        os_type = platform.system()
        print(f"Operating System: {os_type}")
        return os_type

    def check_nmap_installed(self):
        try:
            subprocess.run(["nmap", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("[green]nmap is already installed.[/green]")
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            print("[red]nmap is not installed.[/red]")
            return False

    def check_chocolatey_installed(self):
        try:
            subprocess.run(["choco", "-v"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("[green]Chocolatey is already installed.[/green]")
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            print("[red]Chocolatey is not installed.[/red]")
            return False

    def install_chocolatey(self):
        approval = input("Chocolatey is required to install nmap. Would you like to install Chocolatey? (y/n): ").lower()
        if approval == 'y':
            install_command = '''Set-ExecutionPolicy Bypass -Scope Process -Force; \
[System.Net.WebClient]::new().DownloadString('https://community.chocolatey.org/install.ps1') | Invoke-Expression'''
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
        except (FileNotFoundError, subprocess.CalledProcessError):
            print("[red]Homebrew is not installed.[/red]")
            return False

    def install_homebrew(self):
        approval = input("Homebrew is required to install nmap. Would you like to install Homebrew? (y/n): ").lower()
        if approval == 'y':
            install_command = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
            subprocess.run(install_command, shell=True, check=True)
            print("[green]Homebrew installed successfully.[/green]")
        else:
            print("[yellow]Installation canceled by user.[/yellow]")
            return False
        return True

    def install_nmap(self, os_type):
        approval = input("nmap is not installed. Would you like to download and install it? (y/n): ").lower()
        if approval == 'y':
            if os_type == "Linux":
                distro = platform.linux_distribution()[0] if hasattr(platform, 'linux_distribution') else ""
                if 'Ubuntu' in distro or 'Debian' in distro:
                    subprocess.run(["sudo", "apt-get", "install", "nmap", "-y"], check=True)
                elif 'CentOS' in distro or 'RedHat' in distro:
                    subprocess.run(["sudo", "yum", "install", "nmap", "-y"], check=True)
                else:
                    print("[red]Unsupported Linux distribution. Please install nmap manually.[/red]")
                    return
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
                print("[red]Unsupported operating system. Please install nmap manually.[/red]")
        else:
            print("[yellow]Installation canceled by user.[/yellow]")

    def cli_menu(
        self,
        src_port: Annotated[int, typer.Option("-s", "--srcport", prompt=True, help="Source port that reflects the target service")],
        dst_port: Annotated[int, typer.Option("-d", "--dstport", prompt=True, help="Destination port where the target service is")],
        target: Annotated[str, typer.Option("-t", "--target", prompt=True, help="Victim IP")]
    ):
        # Check and install nmap if necessary
        os_type = self.check_os()
        if not self.check_nmap_installed():
            self.install_nmap(os_type)
            if not self.check_nmap_installed():
                print("[red]nmap installation failed or was canceled. Exiting...[/red]")
                return

        # Proceed with your functionality
        self.spinnersquare(descriptiontask=f"Connecting to {target} at port {dst_port}")

    def spinnersquare(self, descriptiontask: str, delay: float = 5, final_message: str = "Done!"):
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=False,
        ) as progress:
            progress.add_task(description=f"{descriptiontask}...", total=None)
            time.sleep(delay)
        print(f"{final_message}")
