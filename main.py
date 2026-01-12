import typer
import sys
import signal
from MudaleTunnelUI import MudaleTunnelUI
from tunnel_manager import TunnelManager
import config

app = typer.Typer()
tunnel_manager = TunnelManager()


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    print("\n[yellow]Shutting down...[/yellow]")
    tunnels = tunnel_manager.list_tunnels()
    if tunnels:
        print(f"[yellow]Stopping {len(tunnels)} active tunnel(s)...[/yellow]")
        tunnel_manager.stop_all_tunnels()
    sys.exit(0)


@app.command()
def cli():
    """Run MudaleTunnel in CLI mode (default)."""
    signal.signal(signal.SIGINT, signal_handler)
    ui = MudaleTunnelUI(tunnel_manager)
    ui.cli_menu()


@app.command()
def static(
    ssh_user: str = typer.Option(..., "--user", "-u", help="SSH username"),
    ssh_host: str = typer.Option(..., "--host", "-h", help="SSH host"),
    target_host: str = typer.Option(..., "--target", "-t", help="Target host"),
    remote_port: int = typer.Option(..., "--port", "-p", help="Remote port"),
    local_port: int = typer.Option(None, "--local-port", "-l", help="Local port (default: same as remote)"),
    execute: bool = typer.Option(True, "--execute/--no-execute", help="Execute tunnel automatically")
):
    """Create a static SSH tunnel (local port forwarding - ssh -L)."""
    signal.signal(signal.SIGINT, signal_handler)
    ui = MudaleTunnelUI(tunnel_manager)
    ui.create_static_tunnel(ssh_user, ssh_host, target_host, remote_port, local_port, execute)


@app.command()
def dynamic(
    ssh_user: str = typer.Option(..., "--user", "-u", help="SSH username"),
    ssh_host: str = typer.Option(..., "--host", "-h", help="SSH host"),
    local_port: int = typer.Option(None, "--port", "-p", help="Local SOCKS port (default: auto)"),
    execute: bool = typer.Option(True, "--execute/--no-execute", help="Execute tunnel automatically")
):
    """Create a dynamic SSH tunnel (SOCKS proxy - ssh -D)."""
    signal.signal(signal.SIGINT, signal_handler)
    ui = MudaleTunnelUI(tunnel_manager)
    ui.create_dynamic_tunnel(ssh_user, ssh_host, local_port, execute)


@app.command()
def remote(
    ssh_user: str = typer.Option(..., "--user", "-u", help="SSH username (on attacker machine)"),
    ssh_host: str = typer.Option(..., "--host", "-h", help="SSH host (attacker IP)"),
    remote_bind_port: int = typer.Option(..., "--bind-port", "-b", help="Remote bind port (on attacker machine)"),
    target_host: str = typer.Option(..., "--target", "-t", help="Target host (internal service)"),
    target_port: int = typer.Option(..., "--target-port", "-p", help="Target port (internal service)"),
    bind_address: str = typer.Option("127.0.0.1", "--bind-addr", "-a", help="Bind address (default: 127.0.0.1)"),
    execute: bool = typer.Option(True, "--execute/--no-execute", help="Execute tunnel automatically")
):
    """Create a remote SSH tunnel (reverse port forwarding - ssh -R)."""
    signal.signal(signal.SIGINT, signal_handler)
    ui = MudaleTunnelUI(tunnel_manager)
    ui.create_remote_tunnel(ssh_user, ssh_host, remote_bind_port, target_host, target_port, bind_address, execute)


@app.command()
def remote_dynamic(
    ssh_user: str = typer.Option(..., "--user", "-u", help="SSH username (on attacker machine)"),
    ssh_host: str = typer.Option(..., "--host", "-h", help="SSH host (attacker IP)"),
    remote_socks_port: int = typer.Option(..., "--socks-port", "-p", help="Remote SOCKS port (on attacker machine)"),
    bind_address: str = typer.Option("127.0.0.1", "--bind-addr", "-a", help="Bind address (default: 127.0.0.1)"),
    execute: bool = typer.Option(True, "--execute/--no-execute", help="Execute tunnel automatically")
):
    """Create a remote dynamic SSH tunnel (reverse SOCKS proxy - ssh -R port). Requires OpenSSH 7.6+."""
    signal.signal(signal.SIGINT, signal_handler)
    ui = MudaleTunnelUI(tunnel_manager)
    ui.create_remote_dynamic_tunnel(ssh_user, ssh_host, remote_socks_port, bind_address, execute)


@app.command()
def web(
    port: int = typer.Option(config.DEFAULT_WEB_PORT, "--port", "-p", help="Port for web server"),
    host: str = typer.Option(config.DEFAULT_WEB_HOST, "--host", "-h", help="Host for web server")
):
    """Run MudaleTunnel in web interface mode."""
    import uvicorn
    from web_app import app as web_app
    
    # Share tunnel manager instance
    web_app.tunnel_manager = tunnel_manager
    
    print(f"[green]Starting MudaleTunnel web interface...[/green]")
    print(f"[cyan]Open your browser at: http://{host}:{port}[/cyan]")
    
    try:
        uvicorn.run(web_app, host=host, port=port)
    except KeyboardInterrupt:
        print("\n[yellow]Shutting down web server...[/yellow]")
        tunnels = tunnel_manager.list_tunnels()
        if tunnels:
            print(f"[yellow]Stopping {len(tunnels)} active tunnel(s)...[/yellow]")
            tunnel_manager.stop_all_tunnels()


if __name__ == "__main__":
    # Default to CLI mode if no arguments
    if len(sys.argv) == 1:
        signal.signal(signal.SIGINT, signal_handler)
        ui = MudaleTunnelUI(tunnel_manager)
        ui.cli_menu()
    else:
        app()
