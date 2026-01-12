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
