from reliable_socket.reliable_transfer_protocol import ReliableUDPSocket, ReliableTCPSocket
from threading import Thread
import traceback
import os
import json
import logging


BUFFER_SIZE = 1024
MODE_UPLOAD = 'upload'
MODE_DOWNLOAD = 'download'

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s')
logger.setLevel(logging.ERROR)


class Server(Thread):
    def __init__(self, storage, port, host):
        Thread.__init__(self)
        self.port = port
        self.socket = ReliableTCPSocket()
        self.host = host
        self.storage = storage
        self.clients = []

    def set_sw_socket(self):
        self.socket = ReliableUDPSocket(window_size = 1)

    def set_gbn_socket(self):
        self.socket = ReliableUDPSocket(window_size = 4)

    def __setup__(self):
        self.socket.bind((self.host, self.port))
        self.socket.listen()
        logger.info(f"Listening in {self.host} and {self.port}")

    def main_loop(self):
        self.__setup__()
        while True:
            conn, (client_host, client_port) = self.socket.accept()
            logger.info(f'Incoming Connection from {client_host} {client_port}')
            new_client = ServerWorker(client_port, client_host, conn, self.storage)
            new_client.start()
            self.clients.append(new_client)

        logger.info("Cerrando conexiones")
        for client in self.clients:
            client.join()


class ServerWorker(Thread):
    def __init__(self, port, host, socket, source_dir):
        Thread.__init__(self)
        self.port = port
        self.host = host
        self.socket = socket
        self.source_dir = source_dir

    def __close_conection(self):
        self.socket.close()

    def __send_status(self, code, msg):
        response = { "code": code, "msg": msg }
        self.socket.send(json.dumps(response).encode())

    def run(self):
        mode = self.socket.recv(BUFFER_SIZE).decode()
        if mode == MODE_UPLOAD:
            logger.info(f"Client {self.host}:{self.port} mode: {MODE_UPLOAD} - recving")
            self.__send_status(200, "OK - upload")
            self.recv_file()
        elif mode == MODE_DOWNLOAD:
            logger.info(f"Client {self.host}:{self.port} mode: {MODE_DOWNLOAD} - sending")
            self.__send_status(200, "OK - download")
            self.send_file()
        else:
            logger.info("Invalid mode: ", mode)

    def recv_file(self):
        filename = self.socket.recv(BUFFER_SIZE).decode()
        filename = os.path.basename(filename)
        logger.info(f"Client {self.host}:{self.port} filename to save: {filename}")
        self.__send_status(200, "OK - filename")

        file_size = int(self.socket.recv(BUFFER_SIZE).decode())
        logger.info(f"Client {self.host}:{self.port} filename size: {file_size}")
        self.__send_status(200, "OK - file_size")

        recieved_file = open(f"{self.source_dir}/{filename}", 'wb')
        data_recieved = 0
        while True:
            data = self.socket.recv(BUFFER_SIZE)
            data_recieved += len(data)
            logger.debug("Ultimo fragmento leido fue %r", data)
            recieved_file.write(data)
            if data_recieved == file_size:
                logger.info(f"Receiving finished: closing connection {self.host}:{self.port} ")
                break
            logger.info(f"Llevo leidos {data_recieved} de {file_size}")
        logger.info("TERMINO DE GUARDAR EL ARCHIVO")
        recieved_file.close()


    def send_file(self):
        rcv_packet = self.socket.recv(BUFFER_SIZE)
        filename = rcv_packet.decode()
        logger.info(f"Client {self.host}:{self.port} requested file: {filename}")
        try:
            file_requested = open(f"{self.source_dir}/{filename}", 'rb')
            self.__send_status(200, os.path.getsize(f"{self.source_dir}/{filename}"))
            self.socket.recv(BUFFER_SIZE)
            while(True):
                file_buffered = file_requested.read(BUFFER_SIZE)
                while(file_buffered):
                    self.socket.send(file_buffered)
                    file_buffered = file_requested.read(BUFFER_SIZE)
                if not file_buffered:
                    logger.info(f"Sending finished: closing connection {self.host}:{self.port}")
                    file_requested.close()
                    break
        except FileNotFoundError:
            response = {"code": 400}
            self.socket.send(json.dumps(response).encode())
            logger.info(traceback.format_exc())
            self.socket.send(f"file: {filename} not found".encode())
