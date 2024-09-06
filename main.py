from colorama import Fore
import optparse
    
def cli_menu():
    parser = optparse.OptionParser()
    parser.add_option("-sp", "--sourceport",dest="source_port",help="Source port that reflect the target service")
    parser.add_option("-dp", "--sourceport",dest="destenation_port",help="Destenation port where is the target service")
    parser.add_option("-t", "--target",dest="target",help="Victim IP")
