from reliable_socket.reliable_transfer_protocol import ReliableUDPSocket, ReliableTCPSocket
import json
import os
from tqdm import tqdm
import logging


BUFFER_SIZE = 1024
MODE_UPLOAD = 'upload'
MODE_DOWNLOAD = 'download'

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s')
logger.setLevel(logging.ERROR)



class Client():
    def __init__(self, path, filename, host, port=6000):
        self.host = host
        self.port = port
        self.socket = ReliableTCPSocket()
        self.path = path
        self.filename = filename

    def set_sw_socket(self):
        self.socket = ReliableUDPSocket(window_size = 1)

    def set_gbn_socket(self):
        self.socket = ReliableUDPSocket(window_size = 4)

    def __connect(self):
        self.socket.connect((self.host, self.port))

    def __close_conection(self):
        self.socket.close()

    def __send_message(self, message):
        self.socket.send(message.encode())
        rcv_packet = self.socket.recv(BUFFER_SIZE)
        response = json.loads(rcv_packet.decode())
        return response

    def __open_file(self):
        try:
            path = f"{self.path}/{self.filename}"
            file_to_send = open(path, 'rb')
            return file_to_send
        except FileNotFoundError:
            logger.info(f"File not found at {path}. Won't connect to server.")
            exit()

    def upload(self):
        file_to_send = self.__open_file()

        self.__connect()
        res_mode = self.__send_message(MODE_UPLOAD)  # seteo modo
        res_filename = self.__send_message(self.filename)  # mando nombre
        size = os.path.getsize(f"{self.path}/{self.filename}")
        res_file_size = self.__send_message(str(size))  # mando tamaño

        if(res_mode['code'] == res_filename['code'] == res_file_size['code'] == 200):
            # file_to_send = open(f"{self.path}/{self.filename}", 'rb')
            progress_bar = tqdm(total = size)
            while(True):
                file_buffered = file_to_send.read(BUFFER_SIZE)
                while(file_buffered):
                    self.socket.send(file_buffered)
                    progress_bar.update(len(file_buffered))
                    # logger.info(progress_bar)
                    file_buffered = file_to_send.read(BUFFER_SIZE)
                if not file_buffered:
                    progress_bar.close()
                    file_to_send.close()
                    logger.info("Sending finished: closing connection")
                    self.__close_conection()
                    break

    def download(self):
        self.__connect()
        res_mode = self.__send_message(MODE_DOWNLOAD) # seteo modo
        res_filename = self.__send_message(self.filename) # pido nombre

        if(res_mode['code'] == res_filename['code'] == 200):
            filesize = res_filename['msg']
            data_downloaded = 0
            self.socket.send("OK".encode())
            with open(f"{self.path}/{self.filename}", 'wb') as recieved_file:
                progress_bar = tqdm(total = res_filename['msg'])
                while True:
                    data = self.socket.recv(BUFFER_SIZE)
                    data_downloaded += len(data)
                    if progress_bar.n < int(filesize):
                        progress_bar.update(len(data))
                        # logger.info(progress_bar)
                    recieved_file.write(data)
                    if data_downloaded == filesize:
                        recieved_file.close()
                        progress_bar.close()
                        break
        elif(res_mode['code'] == "400"):
            logger.info(f"File: {self.filename} not found")
        logger.info("connection closed")
        self.__close_conection()
