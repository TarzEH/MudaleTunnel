import typer
from MudaleTunnelUI import MudaleTunnelUI


if __name__ == "__main__":
    ui = MudaleTunnelUI()
    ui.printer_menu()
    # typer.run(probar)
    typer.run(ui.cli_menu)
