from socket import socket, SOCK_DGRAM, AF_INET
from threading import Thread
import threading
from time import sleep
from random import randint
import os
from datetime import datetime
from udp.utils import assembly_packet, extract_packet, create_file, file_exists, write_into_file, format_address
from udp.constants import BUF_SIZE, MSG_DOWNLOAD_REQ, TIMEOUTS, TIMEOUT, MSG_INIT, MSG_INITACK, MSG_UPLOAD_REQ, MSG_UPLOAD, MSG_UPLOAD_ACK, MSG_CLOSE, MSG_CLOSE_ACK, MSG_EMPTY, MSG_DOWNLOAD_REQ_ACK, MSG_FILE_NOT_EXISTS, MSG_ERROR, MSG_UPLOAD_REQ_ACK

from udp.udp_packet import UDPPacket


class ClientStates(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.states = {}

    def add_new_client(self, client_addr, packet_sent, packet_recv):
        self.lock.acquire()
        try:
            self.states[f"{client_addr[0]}:{client_addr[1]}"] = {"sent": packet_sent, "recv": packet_recv, "last_sent": datetime.now(), 'timeouts': 0, 'handshake_completed': False}
        finally:
            self.lock.release()

    def remove_client(self, client_addr):
        self.lock.acquire()
        try:
            del self.states[f"{client_addr[0]}:{client_addr[1]}"]
        except KeyError:
            pass
        finally:
            self.lock.release()

    def get_client_state(self, client_addr):
        self.lock.acquire()
        try:
            return self.states[f"{client_addr[0]}:{client_addr[1]}"]
        except:
            return None
        finally:
            self.lock.release()

    def update_client_state(self, client_addr, packet_sent, packet_recv):
        self.lock.acquire()
        try:
            self.states[f"{client_addr[0]}:{client_addr[1]}"]['sent'] = packet_sent
            self.states[f"{client_addr[0]}:{client_addr[1]}"]['recv'] = packet_recv
            self.states[f"{client_addr[0]}:{client_addr[1]}"]['last_sent'] = datetime.now()
            self.states[f"{client_addr[0]}:{client_addr[1]}"]['timeouts'] = 0
        finally:
            self.lock.release()

    def get_timeout_elements(self):
        self.lock.acquire()
        retransmit = dict(filter(lambda client: (datetime.now() - client[1]['last_sent']).total_seconds() > TIMEOUT, self.states.items()))
        self.lock.release()
        return retransmit

    def update_client_timeout(self, addr):
        self.lock.acquire()
        self.states[format_address(addr)]['last_sent'] = datetime.now()
        self.states[format_address(addr)]['timeouts'] += 1
        self.lock.release()

    def connection_established(self, addr, packet):
        self.lock.acquire()
        self.states[format_address(addr)]['handshake_completed'] = True
        self.states[format_address(addr)]['recv'] = packet
        self.lock.release()


# Esto es un thread que recibe un cliente, un paquete y el estado de clientes, se fija en que estado estaba para 
# determinar con el paquete a que proximo estado ira.
# El thread usa su propio socket para mandar paquetes
class ServerWorker(Thread):
    def __init__(self, addr, udp_packet, client_states, source_dir, mode='normal'):
        Thread.__init__(self)
        self.socket = socket(AF_INET, SOCK_DGRAM)
        self.client_addr = addr
        self.udp_packet = udp_packet
        self.source_dir = source_dir
        self.client_states = client_states
        self.mode = mode
        self.sequence_number = randint(0, 100)

    def validate_packet_integrity(self, packet):
        pass

    def __create_initialization_ack_packet(self):
        return UDPPacket(MSG_INITACK, MSG_EMPTY, 0, self.sequence_number)

    def __create_upload_request_ack_packet(self, packet):
        return UDPPacket(MSG_UPLOAD_REQ_ACK, packet.filename, packet.length, packet.sequence_number)

    def __create_download_request_ack_packet(self, packet):
        if(file_exists(packet.filename)):
            filesize = os.path.getsize(packet.filename)
            return UDPPacket(MSG_DOWNLOAD_REQ_ACK, packet.filename, filesize, packet.sequence_number, None)
        else:
            return UDPPacket(MSG_FILE_NOT_EXISTS, packet.filename, 0, packet.sequence_number, None)

    def __create_upload_ack_packet(self, packet, last_packet_sent):
        return UDPPacket(MSG_UPLOAD_ACK, packet.filename, packet.length, last_packet_sent.sequence_number + len(packet.data))

    def __create_close_ack_packet(self, packet):
        return UDPPacket(MSG_CLOSE_ACK, '', 0, packet.sequence_number)

    def __create_invalid_packet(self, packet):
        return UDPPacket(MSG_ERROR, '', 0, packet.sequence_number)

    def __process_init(self, packet):
        client_state = self.client_states.get_client_state(self.client_addr)
        packet_for_client = self.__create_initialization_ack_packet()
        init_ack = assembly_packet(packet_for_client)
        if(client_state is None):  # es la primera vez que viene
            print(f"[SERVER WORKER {format_address(self.client_addr)}] - Establishing connection handshake: {format_address(self.client_addr)}")
            self.client_states.add_new_client(self.client_addr, packet_for_client, packet)
            self.socket.sendto(init_ack, self.client_addr)
        else:  # El cliente envio un init ya teniendo la conexion inicializada, se procede a enviar el ultimo paquete enviado
            print(f"[SERVER WORKER {format_address(self.client_addr)}] - Client already initialized connection, retransmiting last package sent")
            print(f"[SERVER WORKER {format_address(self.client_addr)}] - Re Sending INIT ACK to: {format_address(self.client_addr)}")
            self.socket.sendto(assembly_packet(client_state['sent']), self.client_addr)

    def __finish_three_way_handshake(self, packet):
        client_state = self.client_states.get_client_state(self.client_addr)
        if(client_state['recv'].mode == MSG_INIT):  # TWH completado
            print(f"[SERVER WORKER {format_address(self.client_addr)}] - Client already completed Three way Handshake")
            self.client_states.connection_established(self.client_addr, packet)
        else:
            print(f"[SERVER WORKER {format_address(self.client_addr)}] - Client sent invalid request")
            packet_for_client = self.__create_invalid_packet()
            self.socket.sendto(assembly_packet(packet_for_client), self.client_addr)

    def __process_upload_req(self, packet):
        print(f"[SERVER WORKER {format_address(self.client_addr)}] - Recieved Upload request from client")
        client_state = self.client_states.get_client_state(self.client_addr)
        if((client_state['sent'].mode == MSG_INITACK) & (client_state['handshake_completed'])):  # Inicializo conexion
            packet_to_sent = self.__create_upload_request_ack_packet(packet)
            print(f"[SERVER WORKER {format_address(self.client_addr)}] - Sending UPLOAD ACK to: {format_address(self.client_addr)}")
            self.client_states.update_client_state(self.client_addr, packet_to_sent, packet)  # Actualizado el estado
            upload_req_ack = assembly_packet(packet_to_sent)
            create_file(f"{self.source_dir}/{packet.filename}")  # Reservo el archivo para el upload
            self.socket.sendto(upload_req_ack, self.client_addr)
        else:
            print(f"[SERVER WORKER {format_address(self.client_addr)}] - Client asked for upload req but is not in a valid state, retransmiting last package sent")
            self.socket.sendto(assembly_packet(client_state['sent']), self.client_addr)

    def __process_download_req(self, packet):
        print(f"[SERVER WORKER {format_address(self.client_addr)}] - Recieved Download request from client")
        client_state = self.client_states.get_client_state(self.client_addr)
        if(client_state['sent'].mode == MSG_INITACK): ## Inicializo conexion
            packet_to_sent = self.__create_download_request_ack_packet(packet)
            print(f"[SERVER WORKER {format_address(self.client_addr)}] - Sending DOWNOAD REQ ACK to: {format_address(self.client_addr)}")
            ##### NOSE SI TIENE SENTIDO GUARDAR ESTE ESTADO?
            self.client_states.update_client_state(self.client_addr, packet_to_sent, packet) ## Actualizado el estado
            upload_req_ack = assembly_packet(packet_to_sent)
            self.socket.sendto(upload_req_ack, self.client_addr)
        else:
            print(f"[SERVER WORKER {format_address(self.client_addr)}] - Client asked for upload req but is not in a valid state, retransmiting last package sent")
            self.socket.sendto(assembly_packet(client_state['sent']), self.client_addr)

    def __retransmit_last_packet(self, packet):
        print(f"[SERVER WORKER] - Timeout for client {self.client_addr}, retransmiting last packet sent")
        self.client_states.update_client_timeout(self.client_addr)
        self.socket.sendto(assembly_packet(packet), self.client_addr)

    def __process_upload(self, packet):
        client_state = self.client_states.get_client_state(self.client_addr)
        # print(f"sent: {client_state['sent'].__dict__}, rcv: {client_state['recv'].__dict__}")
        print(f"[SERVER WORKER {format_address(self.client_addr)}] - Recieved Upload {len(packet.data)} bytes from client")
        if(client_state['sent'].sequence_number == packet.sequence_number):
            print(f"[SERVER WORKER {format_address(self.client_addr)}] - File recieved is correct")
            packet_to_sent = self.__create_upload_ack_packet(packet, client_state['sent'])
            self.client_states.update_client_state(self.client_addr, packet_to_sent, packet)
            write_into_file(f"{self.source_dir}/{packet.filename}", packet.data)
            upload_ack = assembly_packet(packet_to_sent)
        else:
            print(f"[SERVER WORKER {format_address(self.client_addr)}] - File is out of order, proceding to re transmit last acked packet")
            upload_ack = assembly_packet(client_state['sent'])
        self.socket.sendto(upload_ack, self.client_addr)

    def __process_close_connection(self, packet):
        print(f"[SERVER WORKER {format_address(self.client_addr)}] - Recieved Close request from client")
        client_state = self.client_states.get_client_state(self.client_addr)
        if(client_state['sent'].mode in [MSG_UPLOAD_ACK, MSG_UPLOAD_ACK]):
            packet_to_sent = self.__create_close_ack_packet(packet)
            print(f"[SERVER WORKER {format_address(self.client_addr)}] - Sending Close ACK to: {format_address(self.client_addr)}")
            self.client_states.update_client_state(self.client_addr, packet_to_sent, packet) ## Actualizado el estado
            close_req_ack = assembly_packet(packet_to_sent)
            self.socket.sendto(close_req_ack, self.client_addr)
        else:
            print(f"[SERVER WORKER {format_address(self.client_addr)}] - Client asked for close req but is not in a valid state, retransmiting last package sent")
            self.socket.sendto(assembly_packet(client_state['sent']), self.client_addr)

    def __process_packet(self, packet):
        if(self.mode == 'normal'):
            if(packet.mode == MSG_INIT):
                self.__process_init(packet)
            elif(packet.mode == MSG_INITACK):
                self.__finish_three_way_handshake(packet)
            elif(packet.mode == MSG_UPLOAD_REQ):
                self.__process_upload_req(packet)
            elif(packet.mode == MSG_DOWNLOAD_REQ):
                self.__process_download_req(packet)
            elif(packet.mode == MSG_UPLOAD):
                self.__process_upload(packet)
            elif(packet.mode == MSG_CLOSE):
                self.__process_close_connection(packet)
        else:
            self.__retransmit_last_packet(packet)

    def run(self):
        packet_recv = extract_packet(self.udp_packet)
        self.__process_packet(packet_recv)


# Este componente se queda escuchando cada 2 segundos si hubo clientes en timeout, si esto sucede, crea un worker nuevo en modo de retransmision
class ServerTimeoutComponent(Thread):
    def __init__(self, states):
        Thread.__init__(self)
        self.states = states
        self.threads = []

    def run(self):
        while True:
            sleep(2)
            resend = self.states.get_timeout_elements()
            if len(resend) > 0:
                print(f"[SERVER TIMEOUT COMPONENT] - Clients timeouted {len(resend)}")
            for client, state in resend.items():
                host, port = client.split(":")
                if((state['sent'].mode == MSG_CLOSE_ACK) or (state['timeouts'] >= TIMEOUTS)):
                    self.states.remove_client(tuple([host, int(port)]))
                else:
                    new_client = ServerWorker(tuple([host, int(port)]), assembly_packet(state['sent']), self.states, None, 'retransmit')
                    new_client.start()


class ServerUDP(Thread):
    def __init__(self, host, port, storage):
        self.socket = socket(AF_INET, SOCK_DGRAM)
        self.addr = (host, port)
        self.socket.bind(self.addr)
        self.storage = storage
        self.client_states = ClientStates()
        self.timeout_component = ServerTimeoutComponent(self.client_states)
        self.timeout_component.start()
        self.workers = []

    def accept_client(self):
        print("[SERVER] - Wait_client...")
        package, client_addr = self.socket.recvfrom(BUF_SIZE)
        return client_addr, package

    def main_loop(self):
        while True:
            addr, package = self.accept_client()
            print(f"[SERVER] - Connection recieved from: {addr[0]}:{addr[1]}")
            new_client = ServerWorker(addr, package, self.client_states, self.storage)
            new_client.start()
            self.workers.append(new_client)


server = ServerUDP('localhost', 5000, './uploads')
server.main_loop()
