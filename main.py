import typer
from typing_extensions import Annotated
from MudaleTunnelUI import MudaleTunnelUI

app = typer.Typer(help="MudaleTunnel - SSH Tunnel Setup Tool")

@app.command()
def scan(
    target: Annotated[str, typer.Argument(help="Target IP or domain to scan")],
    username: Annotated[str, typer.Option("--user", "-u", help="SSH username")] = None,
    ssh_host: Annotated[str, typer.Option("--ssh-host", "-s", help="SSH hostname or IP")] = None,
    port: Annotated[int, typer.Option("--port", "-p", help="Specific port to tunnel")] = None,
    local_port: Annotated[int, typer.Option("--local-port", "-l", help="Local port for tunneling")] = None
):
    """Scan target and optionally set up SSH tunnel with provided arguments."""
    ui = MudaleTunnelUI()
    ui.run_with_args(target, username, ssh_host, port, local_port)

@app.command()
def interactive():
    """Run in interactive mode (default behavior)."""
    ui = MudaleTunnelUI()
    ui.cli_menu()

if __name__ == "__main__":
    app()
