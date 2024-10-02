import typer
from MudaleTunnelUI import MudaleTunnelUI


if __name__ == "__main__":
    ui = MudaleTunnelUI()
    typer.run(ui.cli_menu)
1