import socket
import json
import os
from tqdm import tqdm

BUFFER_SIZE = 1024
MODE_UPLOAD = 'upload'
MODE_DOWNLOAD = 'download'

class ClientTCP():
    def __init__(self, dest_path, filename, host, port=6000):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.dest_path = dest_path
        self.filename = filename

    def __connect(self):
        self.socket.connect((self.host, self.port))

    def __send_message(self, message):
        self.socket.send(message.encode())
        rcv_packet = self.socket.recv(BUFFER_SIZE)
        response = json.loads(rcv_packet.decode())
        return response

    def __open_file(self):
        try:
            path = f"{self.dest_path}/{self.filename}"
            file_to_send = open(path, 'rb')
            return file_to_send
        except FileNotFoundError:
            print(f"File not found at {path}. Won't connect to server.")
            exit()

    def upload(self):
        file_to_send = self.__open_file()

        self.__connect()
        res_mode = self.__send_message(MODE_UPLOAD) # seteo modo
        res_filename = self.__send_message(self.filename) # mando nombre
        size = os.path.getsize(f"{self.dest_path}/{self.filename}")
        res_file_size = self.__send_message(str(size)) # mando tamaño

        if(res_mode['code'] == res_filename['code'] == res_file_size['code'] == 200):
            # file_to_send = open(f"{self.dest_path}/{self.filename}", 'rb')
            progress_bar = tqdm(total = size)
            while(True):
                file_buffered = file_to_send.read(BUFFER_SIZE)
                while(file_buffered):
                    self.socket.send(file_buffered)
                    progress_bar.update(len(file_buffered))
                    # print(progress_bar)
                    file_buffered = file_to_send.read(BUFFER_SIZE)
                if not file_buffered:
                    progress_bar.close()
                    file_to_send.close()
                    print("Sending finished: closing connection")
                    break
        self.socket.close()

    def download(self):
        self.__connect()
        res_mode = self.__send_message(MODE_DOWNLOAD) # seteo modo
        res_filename = self.__send_message(self.filename) # pido nombre

        if(res_mode['code'] == res_filename['code'] == 200):
            self.socket.send("OK".encode())
            with open(f"{self.dest_path}/{self.filename}", 'wb') as recieved_file:
                progress_bar = tqdm(total = res_filename['msg'])
                while True:
                    data = self.socket.recv(BUFFER_SIZE)
                    if progress_bar.n < res_filename['msg']:
                        progress_bar.update(len(data))
                        # print(progress_bar)
                    if not data:
                        recieved_file.close()
                        progress_bar.close()
                        break

                    recieved_file.write(data)

        elif(res_mode['code'] == "400"):
            print(f"File: {self.filename} not found")
            self.socket.close()
        print("connection closed")
