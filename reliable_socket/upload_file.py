import argparse
import socket
from reliable_socket.client import Client
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s')
logger.setLevel(logging.DEBUG)


parser = argparse.ArgumentParser()
parser.add_argument('-v', '--verbose', help="increase output verbosity", action="store_true")
parser.add_argument('-q', '--quiet', help="decrease output verbosity", action="store_true")

parser.add_argument('-p', '--port', help="server port", type=int)
parser.add_argument('-H', '--host', help="host server IP address", default=socket.gethostname())
parser.add_argument('-s', '--src', help="source file path")
parser.add_argument('-n', '--name', help="file name")
parser.add_argument('-P', '--proto', help="protocol tcp, sw (udp stop&wait) or gbn (udp go back n)")

args = parser.parse_args()

if((args.src is not None) and (args.name is not None) and (args.port is not None) and (args.host is not None)):
    client = Client(args.src, args.name, args.host, args.port)
    if args.proto == 'ws':
        client.set_sw_socket()
    elif args.proto == 'gbn':
        client.set_gbn_socket()
    client.upload()
else:
    logger.info("Paramters missing")
    exit()

# para correr:
# python upload_file.py -p 4125 -H localhost -n test.txt -s ./
