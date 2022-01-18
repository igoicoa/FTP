import argparse
import socket
from client import ClientTCP

parser = argparse.ArgumentParser()
parser.add_argument('-v', '--verbose', help="increase output verbosity", action="store_true")
parser.add_argument('-q', '--quiet', help="decrease output verbosity", action="store_true")

parser.add_argument('-p', '--port', help="server port", type=int)
parser.add_argument('-H', '--host', help="host server IP address", default=socket.gethostname())
parser.add_argument('-d', '--dst', help="destination file path")
parser.add_argument('-n', '--name', help="file name")
parser.add_argument('-m', '--mode', help="download / upload", default = 'download')

args = parser.parse_args()

if((args.dst is not None) and (args.name is not None) and (args.port is not None) and (args.host is not None)):
    a = ClientTCP(args.dst, args.name, args.host, args.port)
    getattr(a, args.mode)()
else:
    print("Paramters missing")
    exit()

# para correr:
# python start_client.py -p 4125 -H localhost -n test.txt -d ./
# python start_client.py -p 4125 -H localhost -n test.txt -d ./ -m upload