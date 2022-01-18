from reliable_transfer_protocol import ReliableUDPSocket, logger
import logging
from threading import Thread

sock = ReliableUDPSocket()
sock.bind(('127.0.0.1', 10000))
sock.listen()

"""
logger = logging.getLogger(__name__)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)
"""
logger = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger.setLevel(logging.INFO)

def aux(conn):
    while True:
        logger.info("Test")
        data = conn.sock.recv(1024)
        logger.info("Recibi %s", data)

while True:
    print(f"Espero nueva conexion")
    conn, address = sock.accept()
    print(f"Nueva conexión de {address}")
    assert 1 == 1
    #t = Thread(target=aux, args=(conn,), daemon=True)
    #t.start()
    #print(f"Recibi {data}")
