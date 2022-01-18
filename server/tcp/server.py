import socket
from threading import Thread
import traceback
import os
import json

BUFFER_SIZE = 1024
MODE_UPLOAD = 'upload'
MODE_DOWNLOAD = 'download'

class ServerTCP(Thread):
    def __init__(self, storage, port, host):
        Thread.__init__(self)
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.host = host
        self.storage = storage
        self.clients = []

    def __setup__(self):
        self.socket.bind((self.host, self.port))
        self.socket.listen()
        print(f"Listening in {self.host} and {self.port}")

    def main_loop(self):
        self.__setup__()
        while True:
            conn, (client_host, client_port) = self.socket.accept()
            print(f'Incoming Connection from {client_host} {client_port}')
            new_client = ServerWorker(client_port, client_host, conn, self.storage)
            new_client.start()
            self.clients.append(new_client)

        print("Cerrando conexiones")
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
            print(f"Client {self.host}:{self.port} mode: {MODE_UPLOAD} - recving")
            self.__send_status(200, "OK - upload")
            self.recv_file()
        elif mode == MODE_DOWNLOAD:
            print(f"Client {self.host}:{self.port} mode: {MODE_DOWNLOAD} - sending")
            self.__send_status(200, "OK - download")
            self.send_file()
        else:
            print("Invalid mode: ", mode)
        

    def recv_file(self):
        filename = self.socket.recv(BUFFER_SIZE).decode()
        print(f"Client {self.host}:{self.port} filename to save: {filename}")
        self.__send_status(200, "OK - filename")

        file_size = int(self.socket.recv(BUFFER_SIZE).decode())
        print(f"Client {self.host}:{self.port} filename size: {file_size}")
        self.__send_status(200, "OK - file_size")

        with open(f"{self.source_dir}/{filename}", 'wb') as recieved_file:
                while True:
                    data = self.socket.recv(BUFFER_SIZE)
                    if not data:
                        print(f"Receiving finished: closing connection {self.host}:{self.port} ")
                        recieved_file.close()
                        self.__close_conection()
                        break

                    recieved_file.write(data)

    def send_file(self):
        rcv_packet = self.socket.recv(BUFFER_SIZE)
        filename = rcv_packet.decode()
        print(f"Client {self.host}:{self.port} requested file: {filename}")
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
                    print(f"Sending finished: closing connection {self.host}:{self.port}")
                    file_requested.close()
                    self.__close_conection()
                    break
        except FileNotFoundError:
            response = {"code": 400}
            self.socket.send(json.dumps(response).encode())
            print(traceback.format_exc())
            self.socket.send(f"file: {filename} not found".encode())
