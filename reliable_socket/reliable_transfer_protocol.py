"""
This Module will include a Reliable Transfer Protocol similar to TCP, implemented in UDP
"""
import time
import socket
import logging
import queue
from threading import Thread, Lock, Condition
from abc import ABC, abstractmethod

from utils import UDPPacket, chunked

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s')
logger.setLevel(logging.ERROR)

# CONSTANTS

# MAX PACKET SIZE chosen based on
# https://stackoverflow.com/questions/40032171/find-max-udp-payload-python-socket-send-sendto
MAX_PACKET_SIZE = 1500
WINDOW_SIZE = 4
RTO = 2  # Seconds
RETRANSMISSION_DELAY = 0.1  # Seconds

# STATUSES
STATUS_SYN = 1
STATUS_ESTABLISHED = 2


class ReliableSocket(ABC):
    """
    Abstract Class  to use as a template on what should a Reliable Socket implement

    Method Signatures based on the Python 3 Socket library
    https://docs.python.org/3/library/socket.html
    """
    @abstractmethod
    def connect(self, address: str):
        # Blocking
        # If the remote address isn't listening, it must return inmediately with an error
        # Otherwise it blocks until the connection is established
        pass

    @abstractmethod
    def connect_ex(self, address: str):
        pass

    @abstractmethod
    def bind(self, address: str):
        pass

    @abstractmethod
    def listen(self):
        # Should be NON-Blocking
        pass

    @abstractmethod
    def accept(self):
        # Should be Blocking
        pass

    @abstractmethod
    def send(self, data: bytes):
        pass

    @abstractmethod
    def recv(self, bufsize: int):
        pass

    @abstractmethod
    def close(self):
        pass


class ReliableTCPSocket(socket.socket):
    """
    This class is essentially the common socket using TCP. No custom methods
    """
    def __init__(self):
        super().__init__(family=socket.AF_INET, type=socket.SOCK_STREAM)


class ReliableUDPSocket(ReliableSocket):
    """
    Reliable Socket using UDP Protocol

    This class will be used both for sending and receiving data
    """
    # MAX PACKET SIZE chosen based on
    # https://stackoverflow.com/questions/40032171/find-max-udp-payload-python-socket-send-sendto
    MAX_PACKET_SIZE = 1500
    WINDOW_SIZE = 4
    RTO = 2  # Seconds
    RETRANSMISSION_DELAY = 0.1

    def __init__(self, window_size=WINDOW_SIZE, rto=RTO, rtx_delay=RETRANSMISSION_DELAY):
        # Internal Socket
        self.sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.new_connections_queue = queue.Queue()
        self.server_mode = None
        self.listening_thread = None
        self.retransmission_thread = None
        self.stop_transmission = False
        self.transmit_lock = Lock()
        self.gbn_window = []
        self.connection_status = None  # Only needed for client's 'workers'
        self.id = None
        self.seq_n = 0
        self.r_seq_n = 0
        self.r_seq_n_lock = Lock()
        self.app_sent_buffer = queue.Queue()  # Info sent by the app
        self.app_sent_buffer_lock = Lock()
        self.app_recv_buffer = b''  # Info to be read by the app
        self.app_recv_buffer_lock = Lock()
        self.recv_buffer_cond = Condition()
        self.established_cond = Condition()
        self.can_close_cond = Condition()
        # Configurable Attributes
        self.window_size = window_size
        self.rto = rto
        self.rtx_delay = rtx_delay
        # Used for ending a connection
        self.fin_cond = Condition()
        self.stop_listening = False
        self.desconnected_timeouts = 3

    def bind(self, addr):
        """
        Binds the socket to a local address. Non-Blocking
        """
        self.sock.bind(addr)

    def accept(self):
        """
        Blocks the current execution until a new connection is received through the queue
        :return: (conn, address)
        """
        conn, address = self.new_connections_queue.get()
        conn.server_mode = True
        conn._listen()
        conn._start_retransmission_thread()
        return conn, address

    def connect(self, address):
        """
        Connect to a remote socket at `address`. Blocks the execution until the connection has been
        established
        """
        self.sock.connect(address)
        local_address = self.sock.getsockname()
        self.id = f"Client: {local_address[0]}:{local_address[1]}"
        self.server_mode = False
        self._start_retransmission_thread()
        self._listen()

        package = UDPPacket.create_syn()
        with self.transmit_lock:
            self.gbn_window.append(package)
            package.tick()
            self._send(package)

        # Connect MUST be blocking, it blocks until the connection is fully established with the
        # server. The connect releases once the client receives a SYN+ACK from the server
        with self.established_cond:
            logger.info("Waiting for connection established")
            self.established_cond.wait()

    def connect_ex(self, address):
        self.connect(address)

    def listen(self):
        """
        Enable the server to accept new connections. Non-Blocking
        """
        self.id = 'Main'
        self.server_mode = True
        self._listen_new_connections()

    def send(self, data: bytes):
        """
        Send data to the socket.

        Receives a bytearray and sends it through the socket if there's available space in the
        Go-Back-N Window. If not, save the packages in a buffer
        """
        assert isinstance(data, bytes)
        with self.transmit_lock:
            # Split the bytes into chunks that fit the UDP Package
            for chunk in chunked(data, self.MAX_PACKET_SIZE-UDPPacket.HEADER_SIZE):
                seq_n = self.seq_n + 1
                self.seq_n += 1
                with self.r_seq_n_lock:
                    # TODO: Review the ack_n. Not quite sure
                    pkg = UDPPacket.create_data(seq_n, self.r_seq_n, chunk)

                    if len(self.gbn_window) == self.window_size:
                        # The buffer is full I cannot send any packages
                        # Dump to local buffer
                        self.app_sent_buffer.put(pkg)
                    else:
                        self.gbn_window.append(pkg)
                        self._send(pkg)

        return len(data)

    def recv(self, bufsize: int):
        """
        Receive data from socket. Blocking.

        Reads from the receive buffer. If the buffer is empty, it blocks until it contains data
        """
        with self.recv_buffer_cond:
            logger.debug("ESPERO A PODER LEER ALGO")
            self.recv_buffer_cond.wait_for(self._rec_buffer_nonempty)
            ret = self.app_recv_buffer[:bufsize]
            self.app_recv_buffer = self.app_recv_buffer[bufsize:]
            logger.debug("TERMINO DE LEER")
            logger.debug("LEI %r", ret)
            return ret

    def close(self):
        logger.debug("WAITING CAN CLOSE")
        with self.can_close_cond:
            self.can_close_cond.wait_for(self._can_close)
        logger.debug("NOW CAN CLOSE")
        package = UDPPacket.create_fin()
        with self.transmit_lock:
            self.gbn_window.append(package)
            package.tick()
            self._send(package)

        # Client must notify the server, but server is not obliged to recieve FIN+ACK?
        if(not self.server_mode):
            # Close MUST be blocking, it blocks until the connection is fully established with the
            # server. The connect releases once the client receives a FIN+ACK from the server
            with self.fin_cond:
                logger.info("Waiting for connection closure")
                self.fin_cond.wait()
                logger.info("Connection Finished")

    def getpeername(self):
        """
        Returns the address of the remote host
        """
        try:
            return self.sock.getpeername()
        except OSError:
            return None

    def getsockname(self):
        """
        Returns the addres the sock is binded to
        """
        return self.sock.getsockname()

    def _rec_buffer_nonempty(self):
        """
        Returns whether or not the receive buffer is not empty
        """
        return len(self.app_recv_buffer) != 0

    def _can_close(self):
        return len(self.gbn_window) == 0 and self.app_sent_buffer.empty()

    def _fork(self, remote_address):
        """
        Returns a "copy" of ReliableUDPSocket

        This is a new socket, it is binded to the same address as the sock we're forking from, but
        it's remote address is set to a client's address. This socket will be the one communicating
        with the client once a connection is initialized (SYN).
        Therefore we will have one "fork" for each client connected to the server
        """
        new_socket = ReliableUDPSocket()
        new_socket.bind(self.sock.getsockname())
        new_socket.sock.connect(remote_address)
        new_socket.id = f"Server: {remote_address[0]}:{remote_address[1]}"
        return new_socket

    def release_resources(self):
        self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()

    def _listen_new_connections(self):
        """
        Listening threads serves two purposes:

         - SERVER: While the main thread should be blocked by the `accept` method, the listening
                   thread will be listening (duh) for incoming packets, which can either be new
                   connection requests OR data sent by an already established connection
         - CLIENT: The listening thread will be listening for replies from the server
        """
        if not self.listening_thread:
            self.listening_thread = Thread(name=f'{self.id}-Listener',
                                           target=self._start_listening_connections,
                                           daemon=True)
            self.listening_thread.start()

    def _listen(self):
        print(self.listening_thread)
        if not self.listening_thread:
            self.listening_thread = Thread(name=f'{self.id}-Listener',
                                           target=self._start_listening,
                                           daemon=True)
            self.listening_thread.start()

    def _start_retransmission_thread(self):
        if not self.retransmission_thread:
            self.retransmission_thread = Thread(name=f'{self.id}-Tx',
                                              target=self._start_retransmission,
                                              daemon=True)
            self.retransmission_thread.start()

    def _start_retransmission(self):
        """
        Method in charge of checking timeouts and retransmitting packages
        """
        while True:
            try:
                # Wait for Retransmission timeout
                # TODO: Validate time of sleep, should be less than RTO
                time.sleep(ReliableUDPSocket.RTO)

                if self.stop_transmission and not self.server_mode:
                    self.stop_listening = True
                    self.release_resources()
                    break
                elif self.stop_transmission and self.server_mode and self.desconnected_timeouts > 0:
                    self.desconnected_timeouts -= 1
                elif self.desconnected_timeouts == 0:
                    logger.debug(f"Server is not transmitting any more to client {self.getpeername()}")
                    self.stop_listening = True
                    self.release_resources()
                    break

                #if not self.connected_to and len(self.sent_buffer) == 0:
                #    return
                # Retransmission of data frames
                with self.transmit_lock:
                    logger.debug("CURRENT TRANSMIT BUFFER %r", self.gbn_window)
                    if any(p.expired(self.RTO) for p in self.gbn_window):
                        # We must retransmit the whole window
                        for packet in self.gbn_window:
                            #if packet.expired(self.RTO):
                            # Retransmitting packet
                            logger.debug(f'[{self.id}] retransmitting %r due to timeout',
                                         packet)
                            packet.tick()
                            # TODO: Should I change the ACK_NUMBER?
                            self._send(packet, retransmit=True)
                    # TODO: Remove, this is for testing.. Just one RTO
                    # self.gbn_window = []
            except Exception as e:
                logger.error("Exception: {}".format(str(e)))
                return

    def _send(self, package, retransmit=False):
        """
        Sends a package through the socket
        """
        self.sock.send(package.to_bytes())

    def _start_listening_connections(self):
        """
        Listens to new connections

        This should only run on the MAIN Server for estabishing new connections,
        which sock is: laddr ip:port, raddr: 0.0.0.0:* (listens any remote address)
        """
        logger.info("Listening with sock laddr: %r, raddr: %r",
                    self.getsockname(),
                    self.getpeername())
        while True:
            logger.info("Haciendo escucha")
            # TODO: Is a lock required?
            # Mepa que no, porque este sock solo tiene laddr y no tiene raddr (0.0.0.0:*)
            # Por lo que es un sock que sólo se usa para iniciar las conexiones
            data, address = self.sock.recvfrom(self.MAX_PACKET_SIZE)

            packet = UDPPacket.from_bytes(data)
            logger.info("Received from %r, packet %r", address, packet)

            if not packet.is_syn():
                logger.info("Packet is not SYN, therefore should not be able to set a connection")
                continue
            # TODO: Debería validar 2 cosas
            #  1) Que sea un SYN. De no ser un SYN el protocolo se rompe.
            #  2) Si es un SYN y ya tenemos una conexión con dicho remote_address, en teoria tenemos
            #     un problema, porque ese paquete debería haber llegado a un sock con una conexión
            #     ya establecida
            # if address not in self.connections_table:
            new_socket = self._fork(address)
            logger.debug("creando socket")
            # self.connections_table[address] = new_socket
            logger.debug(self.new_connections_queue)
            self.new_connections_queue.put((new_socket, address))

            """
            else:
                self.connections_table[address] += 1
                logger.info("Another package received from %r, total %d",
                            address,
                            self.connections_table[address])
            """

    def _start_listening(self):
        """
        Listens for incoming packets from already started connections (doesn't mean estabished)
        """
        self.connection_status = STATUS_SYN
        logger.debug(f"{self.connection_status} - {self.server_mode}")
        """
        When entering this method as a server-mode, it means a client had sent a SYN package.
        Therefore we must send the due SYN+ACK to the client
        """
        if self.server_mode:
            synack_pkg = UDPPacket.create_synack()
            self.sock.send(synack_pkg.to_bytes())
            logger.info("sent SYN+ACK package %r", synack_pkg)

        logger.info("listening with sock laddr: %r, raddr: %r",
                    self.getsockname(),
                    self.getpeername())
        while True:

            logger.info("Haciendo escucha")
            # TODO: Is a lock required?
            # Mepa que no, porque este sock solo tiene laddr y no tiene raddr (0.0.0.0:*)
            # Por lo que es un sock que sólo se usa para iniciar las conexiones
            data, address = self.sock.recvfrom(self.MAX_PACKET_SIZE)

            if self.stop_listening:
                logger.debug(f"Server is not listening any more to client {self.getpeername()}")
                with self.recv_buffer_cond:
                    logger.debug(f"Buffer is... %r", self.app_recv_buffer)
                break

            packet = UDPPacket.from_bytes(data)
            logger.info("Received from %r, packet %r", address, packet)

            if self.server_mode and packet.is_syn() and self.connection_status == STATUS_SYN:
                # Server receives a SYN (duplicate)
                # We have already sent a SYN+ACK. Receiveing a new SYN from the same client
                # means either the package was lost or was received after the timeout and the
                # client sent a new SYN. Therefore we must re-send the SYN+ACK
                synack_pkg = UDPPacket.create_synack()
                self.sock.send(synack_pkg.to_bytes())
                logger.info("Sent SYN+ACK package %r", synack_pkg)

            elif self.server_mode and packet.is_ack() and packet.ack_n == 0 and self.connection_status == STATUS_SYN:
                # Server receives an ACK (to its SYN+ACK)
                self.connection_status = STATUS_ESTABLISHED
                logger.debug("Connection established")
            elif not self.server_mode and packet.is_synack() and self.connection_status == STATUS_SYN:
                # Client receives a SYN+ACK
                logger.debug("Received SYN+ACK.. Sending ACK")
                with self.transmit_lock:
                    pkg = min(self.gbn_window)
                    assert pkg.is_syn()
                    assert pkg.seq_n == packet.ack_n
                    self.gbn_window.remove(pkg)
                self.connection_status = STATUS_ESTABLISHED
                self.sock.send(UDPPacket.create_ack(0, 0).to_bytes())

                # Notify the reception of the SYN+ACK
                with self.established_cond:
                    logger.debug("Releasing established condition")
                    self.established_cond.notify()
            elif packet.is_ack() and self.connection_status == STATUS_ESTABLISHED:
                # Either Server o Client received an ACK for a package
                with self.transmit_lock:
                    if not self.gbn_window:
                        logger.debug("No packages to ACK")
                        continue

                    if not any(p.seq_n==packet.ack_n for p in self.gbn_window):
                        # The ack isn't of any of the packages contained in the buffer
                        logger.debug("ACK number doesn't match any package in the window")
                        continue
                    else:
                        for buff in self.gbn_window:
                            if buff.seq_n <= packet.ack_n:
                                self.gbn_window.remove(buff)

                    # TODO: Deprecated
                    """
                    min_pkg = min(self.gbn_window)
                    # TODO: FIX. Actually we must remove from the buffer, ALL packages whose seq_n
                    # is <= than the ACK. We might have lost an ACK
                    if min_pkg.seq_n != packet.ack_n:
                        logger.debug("ACK Number doesnt match the min SEQ_N in window")
                        # Do Nothing
                        continue

                    self.gbn_window.remove(min_pkg)
                    """

                    # We now have more space in the window
                    while not self.app_sent_buffer.empty() and len(self.gbn_window) < self.window_size:
                        new_pkg = self.app_sent_buffer.get()
                        # Update the package timestamp
                        new_pkg.tick()
                        # Update the package ack_number
                        with self.r_seq_n_lock:
                            new_pkg.ack_n = self.r_seq_n
                        # Insert it into the transmit buffer and send it
                        self.gbn_window.append(new_pkg)
                        self._send(new_pkg)

                    if self.app_sent_buffer.empty() and len(self.gbn_window) == 0:
                        with self.can_close_cond:
                            self.can_close_cond.notify()
            elif packet.is_data():
                if self.connection_status == STATUS_SYN and self.server_mode:
                    # We might have lost the client's ACK of the three way handshake
                    if packet.seq_n == 1:
                        self.connection_status = STATUS_ESTABLISHED
                        logger.debug("Connection established")
                    else:
                        logger.debug("SYN Status and received a DATA package that isn't the first")
                        continue

                logger.debug("Received DATA")
                with self.r_seq_n_lock:
                    if self.r_seq_n + 1 == packet.seq_n:
                        # It is a new package, one we haven't processed yet
                        self.r_seq_n += 1
                        with self.recv_buffer_cond:
                            if packet.seq_n == 67:
                                logger.debug("EL PAYLOAD ES %r", packet.payload)
                            self.app_recv_buffer += packet.payload
                            self.recv_buffer_cond.notify()

                        with self.transmit_lock:
                            ack = UDPPacket.create_ack(self.seq_n, packet.seq_n)
                            self._send(ack)
                    elif packet.seq_n <= self.r_seq_n:
                        # It is a package we've already processed. The client might not have received
                        # the ACK
                        with self.transmit_lock:
                            ack = UDPPacket.create_ack(self.seq_n, packet.seq_n)
                            self._send(ack)
                    else:
                        # Packet arrived out of order, discarding
                        # We send an ACK with the seq_n of the last package we acked.
                        logger.debug("Packet received out of order")
                        with self.transmit_lock:
                            ack = UDPPacket.create_ack(self.seq_n, self.r_seq_n)
                            self.gbn_window.append(ack)
                            self._send(ack)
            elif self.server_mode and packet.is_fin() and self.connection_status == STATUS_ESTABLISHED:
                # Server receives a FIN
                finack_pkg = UDPPacket.create_finack()
                self.sock.send(finack_pkg.to_bytes())
                logger.info("Sent FIN+ACK package %r", finack_pkg)
                self.stop_transmission = True
            elif not self.server_mode and packet.is_finack() and self.connection_status == STATUS_ESTABLISHED:
                # Client receives FIN+ACK
                with self.fin_cond:
                    pkg = min(self.gbn_window)
                    assert pkg.is_fin()
                    self.gbn_window.remove(pkg)
                    logger.debug("Releasing closing condition")
                    self.stop_transmission = True
                    self.fin_cond.notify()
            else:
                logger.debug("Bad Package")
