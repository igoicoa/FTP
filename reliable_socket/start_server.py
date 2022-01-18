import argparse
import socket
from reliable_socket.server import Server
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s')
logger.setLevel(logging.DEBUG)


parser = argparse.ArgumentParser()
parser.add_argument('-v', '--verbose', help="increase output verbosity", action="store_true")
parser.add_argument('-q', '--quiet', help="decrease output verbosity", action="store_true")

parser.add_argument('-p', '--port', help="service port", type=int)
parser.add_argument('-H', '--host', help="service IP address", default=socket.gethostname())
parser.add_argument('-s', '--storage', help="storage dir path]")
parser.add_argument('-P', '--proto', help="protocol tcp, sw (udp stop&wait) or gbn (udp go back n)")

args = parser.parse_args()

logger.info(args)
if((args.storage is not None) and (args.port is not None) and (args.host is not None)):
    server = Server(args.storage, args.port, args.host)
    if args.proto == 'ws':
        server.set_sw_socket()
    elif args.proto == 'gbn':
        server.set_gbn_socket()
    server.main_loop()
else:
    logger.info("Paramters missing")
    exit()

# para correr:
# python start_server.py -p 4125 -H localhost -s .