from colorama import Fore
import optparse
    
def cli_menu():
    parser = optparse.OptionParser()
    parser.add_option("-s", "--sourceport",dest="source_port",help="Source port that reflect the target service",)
    parser.add_option("-d", "--destenationport",dest="destenation_port",help="Destenation port where is the target service",)
    parser.add_option("-t", "--target",dest="target",help="Victim IP",)

if __name__ == "__main__":
    cli_menu()
