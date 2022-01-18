import os
import traceback
from time import sleep
from random import randint
from socket import socket, AF_INET, SOCK_DGRAM
from udp.udp_packet import UDPPacket
from udp.utils import assembly_packet, extract_packet
from udp.constants import BUF_SIZE, DATA_SIZE, MSG_DOWNLOAD, MSG_DOWNLOAD_REQ_ACK, TIMEOUT, MSG_INIT, MSG_UPLOAD_REQ, MSG_DOWNLOAD_REQ, MSG_UPLOAD, MSG_UPLOAD_ACK, MSG_CLOSE, MSG_EMPTY, MSG_INITACK, MSG_UPLOAD_REQ_ACK, MSG_FILE_NOT_FOUND, MSG_UPLOAD_ERROR


MODE = "UPLOAD"
FILE_REQUEST_UPLOAD = "./udp/file.txt"
FILE_REQUEST_DOWNLOAD = "./file.txt"

NAME_FILE = "new_file.txt"
PATH_DST = "./"


class ClientUDP():
    def __init__(self, host, port, dst, name):
        self.socket = socket(AF_INET, SOCK_DGRAM)
        self.server_addr = (host, port)
        self.file_name = dst + name
        self.socket.settimeout(TIMEOUT)
        self.sequence_number = randint(0, 100)
        self.to_ack = self.sequence_number
        self.last_packet_acked = None
        self.download_size = 0

    def generate_init_packet(self):
        return assembly_packet(UDPPacket(MSG_INIT, MSG_EMPTY, 0, self.sequence_number))

    def generate_init_ack_packet(self):
        return assembly_packet(UDPPacket(MSG_INITACK, MSG_EMPTY, 0, self.sequence_number))

    def generate_upload_req_packet(self, filename):
        filesize = os.path.getsize(filename)
        upload_filename = os.path.basename(filename)
        return assembly_packet(UDPPacket(MSG_UPLOAD_REQ, upload_filename, filesize, self.sequence_number))

    def generate_download_req_packet(self, filename):
        download_filename = os.path.basename(filename)
        return assembly_packet(UDPPacket(MSG_DOWNLOAD_REQ, download_filename, 0, self.sequence_number))

    def generate_upload_package(self, filename, data):
        filesize = os.path.getsize(filename)
        upload_filename = os.path.basename(filename)
        return assembly_packet(UDPPacket(MSG_UPLOAD, upload_filename, filesize, self.sequence_number, data))

    def generate_download_packet(self, filename, data=''):
        return assembly_packet(UDPPacket(MSG_DOWNLOAD, filename, self.download_size, self.to_ack, data))

    def generate_close_packet(self):
        return assembly_packet(UDPPacket(MSG_CLOSE, '', 0, self.sequence_number, ''))

    def connect_server(self):
        while True:
            packet = self.generate_init_packet()
            try:
                self.socket.sendto(packet, self.server_addr)
                data, addr = self.socket.recvfrom(BUF_SIZE)
                packet_rcv = extract_packet(data)
                print(f"[CLIENT] - response: {vars(packet_rcv)}")
                if(packet_rcv.mode == MSG_INITACK):
                    self.last_packet_acked = packet
                    packet = self.generate_init_ack_packet()
                    self.socket.sendto(packet, self.server_addr)
                    return packet, addr
            except:# Timeout, vuelve a enviar el INIT
                traceback.print_exc()
                pass

    def request_upload(self, filename):
        while True:
            packet = self.generate_upload_req_packet(filename)
            try:
                self.socket.sendto(packet, self.server_addr)
                print("[CLIENT] - Upload Request sent, waiting for UPLOAD ACK")
                data, addr = self.socket.recvfrom(BUF_SIZE)
                packet_recv = extract_packet(data)
                print(f"[CLIENT] - response: {vars(packet_recv)}")
                if(packet_recv.mode == MSG_UPLOAD_REQ_ACK):
                    self.last_packet_acked = packet
                    self.send_file(filename)
                elif(packet_recv.mode == MSG_UPLOAD_ERROR):
                    return packet, addr
            except:  # Timeout, vuelve a enviar el INIT
                pass

    def request_download(self, filename):
        self.download_size = 0
        while True:
            packet = self.generate_download_req_packet(filename)
            try:
                self.socket.sendto(packet, self.server_addr)
                print("[CLIENT] - Download Request sent, waiting for DOWNLOAD ACK")
                data, addr = self.socket.recvfrom(BUF_SIZE)
                packet_recv = extract_packet(data)
                print(f"[CLIENT] - response: {vars(packet)}")
                if(packet_recv.mode == MSG_DOWNLOAD_REQ_ACK):
                    self.last_packet_acked = packet
                    self.to_ack = packet_recv.sequence_number
                    self.download_size = packet_recv.length
                    self.download_file(filename)
                    return packet, addr
                elif(packet_recv.mode == MSG_FILE_NOT_FOUND):
                    self.last_packet_acked = packet
                    return packet, addr
            except:# Timeout, vuelve a enviar el INIT
                pass

    def close_connection(self):
        while True:
            packet = self.generate_close_packet()
            try:
                self.socket.sendto(packet, self.server_addr)
                print("[CLIENT] - Send close connection request")
                data, addr = self.socket.recvfrom(BUF_SIZE)
                packet = extract_packet(data)
                print(f"[CLIENT] - response: {vars(packet)}")
                break
            except:# Timeout, vuelve a enviar el INIT
                pass
        self.socket.close()

    def send_file(self, filename):
        filesize = os.path.getsize(filename)
        file = open(filename, "r")
        read_next = True
        while True:
            if(filesize == 0):
                print("[CLIENT] - Upload Complete")
                break
            else:
                if(read_next):
                    data_to_send = file.read(DATA_SIZE)
                    filesize -= len(data_to_send)
                    self.to_ack = self.sequence_number + min(DATA_SIZE, len(data_to_send))
                read_next = False
                packet = self.generate_upload_package(filename, data_to_send)
                try:
                    self.socket.sendto(packet, self.server_addr)
                    print("[CLIENT] - Upload packet sent, waiting for UPLOAD ACK")
                    data, addr = self.socket.recvfrom(BUF_SIZE)
                    packet_recv = extract_packet(data)
                    print(f"[CLIENT] - response: {vars(packet_recv)}")
                    if((packet_recv.mode == MSG_UPLOAD_ACK) and (packet_recv.sequence_number == self.to_ack)):
                        read_next = True
                        self.sequence_number = self.to_ack
                    else:
                        print("[CLIENT] - Retransmiting last packet")
                        self.socket.sendto(packet, self.server_addr)
                        print("[CLIENT] - Upload packet sent, waiting for UPLOAD ACK")
                except:
                    print("[CLIENT] - Timeout, proceeding to retransmit")
                    pass

    def notify_download_completed(self):
        while True:
            packet = self.generate_download_packet(MSG_DOWNLOAD, filename, self.download_size, self.sequence_number, 'OK')
            try:
                self.socket.sendto(packet, self.server_addr)
                print("[CLIENT] - Download complete, Notifing Server")
                data, addr = self.socket.recvfrom(BUF_SIZE)
                packet_recv = extract_packet(data)
                print(f"[CLIENT] - response: {vars(packet_recv)}")
                if((packet_recv.mode == MSG_DOWNLOAD) and (packet_recv.data == 'OK')):
                    return True
                else:
                    print("[CLIENT] - Retransmiting last packet")
                    self.socket.sendto(packet, self.server_addr)
                    print("[CLIENT] - Upload packet sent, waiting for UPLOAD ACK")

            except:
                print("[CLIENT] - Timeout, proceeding to retransmit")
                pass

    def download_file(self, filename):
        file = open(filename, "w")
        bytes_written = 0
        while True:
            packet = self.generate_download_packet(MSG_DOWNLOAD, filename, self.download_size, self.sequence_number)
            try:
                self.socket.sendto(packet, self.server_addr)
                print("[CLIENT] - Download packet sent, waiting for DOWNLOAD ACK")
                data, addr = self.socket.recvfrom(BUF_SIZE)
                packet_recv = extract_packet(data)
                print(f"[CLIENT] - response: {vars(packet_recv)}")
                if((packet_recv.mode == MSG_DOWNLOAD) and (packet_recv.sequence_number == self.to_ack)):
                    self.to_ack += len(packet_recv.data)
                    bytes_written += len(packet_recv.data)
                    file.write(packet_recv.data)
                else:
                    print("[CLIENT] - Retransmiting last packet")
                    self.socket.sendto(packet, self.server_addr)
                    print("[CLIENT] - Upload packet sent, waiting for UPLOAD ACK")

                if(bytes_written == self.download_size):
                    file.close()
                    return self.notify_download_completed()
            except:
                print("[CLIENT] - Timeout, proceeding to retransmit")
                pass

    def run(self):
        print("[CLIENT] - Establishing connection with server")
        data, addr = self.connect_server()
        print("[CLIENT] - Connection established")

        if(MODE == 'UPLOAD'):
            data, addr = self.request_upload(FILE_REQUEST_UPLOAD)
            print("File Uploaded")
        else:
            data, addr = self.request_download(FILE_REQUEST_DOWNLOAD)
            print("File Downloaded")

        self.close_connection()
        print("[CLIENT] - Connection closed")


recv = ClientUDP("localhost", 5000, PATH_DST, NAME_FILE)
recv.run()
