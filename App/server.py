import socket
import threading
import os 
import time

# --- SERVER CONFIGURATION ---
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 9000
BUFFER_SIZE = 1024
# ----------------------------

class FileIndex:
    """
    Manages the mapping between file names and the peers that share them.
    file_index maps: file_name -> set of (ip, port) tuples
    """

    def __init__(self):
        self.file_index = {}
        self.lock = threading.Lock()

    def publish_file(self, file_name, peer_address):
        """Add a peer that publishes a given file."""
        with self.lock:
            if file_name not in self.file_index:
                self.file_index[file_name] = set()
            self.file_index[file_name].add(peer_address)

    def unpublish_file(self, file_name, peer_address):
        """Remove a peer from a published file."""
        with self.lock:
            if file_name in self.file_index and peer_address in self.file_index[file_name]:
                self.file_index[file_name].remove(peer_address)
                if not self.file_index[file_name]:
                    del self.file_index[file_name]
                return True
            return False

    def get_peers(self, file_name):
        """Return all peers that have the given file."""
        with self.lock:
            if file_name in self.file_index:
                return list(self.file_index[file_name])
            return []

    def list_files(self):
        """Return all files and their associated peers."""
        with self.lock:
            return {
                file_name: list(peers)
                for file_name, peers in self.file_index.items()
            }


class NetworkHandler:
    """
    Provides network-related utility methods:
    - Checking internet connectivity
    - Binding socket safely
    """

    @staticmethod
    def check_network_connection(ip="8.8.8.8", port=53):
        """Check if the server can connect to the internet."""
        try:
            socket.setdefaulttimeout(None)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((ip, port))
            return True
        except OSError:
            return False

    @staticmethod
    def bind_socket(host, port):
        """Attempt to bind a socket; return socket object or prompt for new port."""
        while True:
            try:
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server_socket.bind((host, port))
                server_socket.listen(5)
                print(f"[LISTENING] Server listening on {host}:{port}")
                return server_socket
            except OSError as e:
                print(f"[ERROR] Cannot bind to {host}:{port} — {e}")
                try:
                    new_port = input("Enter a new port number to retry: ").strip()
                    port = int(new_port)
                except ValueError:
                    print("Invalid input. Using default port 9000.")
                    port = DEFAULT_PORT


class ClientHandler(threading.Thread):
    """
    Handles communication with a single connected client in a separate thread.
    """

    def __init__(self, client_socket, client_address, file_index):
        super().__init__(daemon=True)
        self.client_socket = client_socket
        self.client_address = client_address
        self.file_index = file_index

    def run(self):
        """Main client communication loop."""
        print(f"[NEW CONNECTION] {self.client_address} connected.")
        try:
            while True:
                message = self.client_socket.recv(BUFFER_SIZE).decode('utf-8')
                if not message:
                    break  # Client disconnected
                print(f"[REQUEST] Received from {self.client_address}: {message}")
                self.process_command(message)
        except ConnectionResetError:
            print(f"[DISCONNECTED] Client {self.client_address} disconnected abruptly.")
        except Exception as e:
            print(f"[ERROR] Error handling client {self.client_address}: {e}")
        finally:
            print(f"[CLOSED] Connection from {self.client_address} closed.")
            self.client_socket.close()

    def process_command(self, message):
        """Parse and execute a client command."""
        parts = message.split()
        if not parts:
            return

        command = parts[0].upper()

        if command == 'PUBLISH' and len(parts) == 3:
            file_name = parts[1]
            peer_port = int(parts[2])
            peer_address = (self.client_address[0], peer_port)
            self.file_index.publish_file(file_name, peer_address)
            print(f"[PUBLISH] Peer {peer_address} added file: {file_name}")
            self.client_socket.sendall(b'PUBLISH_OK')

        elif command == 'UNPUBLISH' and len(parts) == 3:
            file_name = parts[1]
            peer_port = int(parts[2])
            peer_address = (self.client_address[0], peer_port)
            success = self.file_index.unpublish_file(file_name, peer_address)
            if success:
                print(f"[UNPUBLISH] {peer_address} removed {file_name}")
                self.client_socket.sendall(b'UNPUBLISH_OK')
            else:
                self.client_socket.sendall(b'UNPUBLISH_NOT_FOUND')

        elif command == 'FETCH' and len(parts) == 2:
            file_name = parts[1]
            peers = self.file_index.get_peers(file_name)
            if not peers:
                print(f"[FETCH] File not found: {file_name}")
                self.client_socket.sendall(b'FETCH_NOT_FOUND')
            else:
                response = 'PEERS ' + ' '.join([f"{ip}:{port}" for ip, port in peers])
                print(f"[FETCH] Sending peers for {file_name}: {response}")
                self.client_socket.sendall(response.encode('utf-8'))

        elif command == 'PEERS' and len(parts) == 2:
            file_name = parts[1]
            peers = self.file_index.get_peers(file_name)
            if peers:
                response = '\n'.join([f"{ip}:{port}" for ip, port in peers])
                self.client_socket.sendall(response.encode('utf-8'))
            else:
                self.client_socket.sendall(b'NO_PEERS')

        elif command == 'LIST':
            files = self.file_index.list_files()
            if not files:
                self.client_socket.sendall(b'NO_FILES')
            else:
                response_lines = []
                for file_name, peers in files.items():
                    peer_str = ', '.join([f"{ip}:{port}" for ip, port in peers])
                    response_lines.append(f"{file_name} -> {peer_str}")
                response = '\n'.join(response_lines)
                self.client_socket.sendall(response.encode('utf-8'))

        else:
            self.client_socket.sendall(b'UNKNOWN_COMMAND')


class P2PServer:
    """
    Centralized Index Server for the P2P File Sharing System.
    """

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.file_index = FileIndex()
        self.network_handler = NetworkHandler()
        self.server_socket = None

    def monitor_network(self):
        """Continuously monitor internet connection, auto-shutdown if lost."""
        while True:
            if not self.network_handler.check_network_connection():
                print("\n[NETWORK ERROR] Network connection lost. Shutting down server.")
                os._exit(1)
            time.sleep(5)
            
    def start(self):
        """Initialize and start the server."""
        print("=== Centralized Index Server ===")

        if not self.network_handler.check_network_connection():
            print("[ERROR] No network connection detected. Server cannot start.")
            exit(1)

        monitor_thread = threading.Thread(target=self.monitor_network, daemon=True)
        monitor_thread.start()
        self.server_socket = self.network_handler.bind_socket(self.host, self.port)

        try:
            while True:
                client_socket, client_address = self.server_socket.accept()
                handler = ClientHandler(client_socket, client_address, self.file_index)
                handler.start()
        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Server is shutting down.")
        finally:
            if self.server_socket:
                self.server_socket.close()


if __name__ == "__main__":
    host_input = input(f"Enter host (default {DEFAULT_HOST}): ").strip() or DEFAULT_HOST
    try:
        port_input = int(input(f"Enter port (default {DEFAULT_PORT}): ").strip() or DEFAULT_PORT)
    except ValueError:
        port_input = DEFAULT_PORT

    server = P2PServer(host_input, port_input)
    server.start()
