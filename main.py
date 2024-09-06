from colorama import Fore
import optparse

def cli_menu():
    parser = optparse.OptionParser(
        usage="Usage: %prog [options]",
        description="This is a simple CLI tool to specify ports and target."
    )
    
    parser.add_option("-s", "--sourceport", dest="source_port", help="Source port that reflects the target service")
    parser.add_option("-d", "--destenationport", dest="destenation_port", help="Destination port where the target service is")
    parser.add_option("-t", "--target", dest="target", help="Victim IP")


    (options, args) = parser.parse_args()

    print(options)
    return options, args

if __name__ == "__main__":
   print(Fore.GREEN)
   (options, args) = cli_menu()
