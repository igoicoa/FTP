import argparse
import socket
from server import ServerTCP

parser = argparse.ArgumentParser()
parser.add_argument('-v', '--verbose', help="increase output verbosity", action="store_true")
parser.add_argument('-q', '--quiet', help="decrease output verbosity", action="store_true")

parser.add_argument('-p', '--port', help="service port", type=int)
parser.add_argument('-H', '--host', help="service IP address", default=socket.gethostname())
parser.add_argument('-s', '--storage', help="storage dir path]")

args = parser.parse_args()

if((args.storage is not None) and (args.port is not None) and (args.host is not None)):
    a = ServerTCP(args.storage, args.port, args.host)
    a.main_loop()
else:
    print("Paramters missing")
    exit()

# para correr:
# python start_server.py -p 4125 -H localhost -s .