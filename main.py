import sys
import time
from click import prompt
import typer
from typing_extensions import Annotated
from rich.progress import track
from graphic import printer_menu, writer, probar, spinnersquare

import socket
myip = [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]



#the menu 
def cli_menu(
    src_port: Annotated[int, typer.Option("-s","--srcport", prompt=True, 
                                          help="Source port that reflects the target service")],
    dst_port: Annotated[int, typer.Option("-d","--dstport", prompt=True, 
                                          help="Destination port where the target service is")],
    target: Annotated[str, typer.Option("-t", "--target", prompt=True ,help="Victim IP")]
):
    spinnersquare(descriptiontask=f"connecting to {target} at port: {dst_port}")


if __name__ == "__main__":
    printer_menu()
    # typer.run(probar)
    typer.run(cli_menu)