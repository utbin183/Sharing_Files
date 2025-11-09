import socket
import threading
import os
import time
import queue 

# --- CLIENT CONFIGURATION ---
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 9000
PEER_PORT = 9001
CLIENT_REPO_PATH = 'client_files'
local_repository = {}
BUFFER_SIZE = 8192
# -----------------------------


class NetworkHandler:
    """Handles network utility operations like checking connectivity."""

    @staticmethod
    def check_network_connection(ip="8.8.8.8", port=53):
        try:
            socket.setdefaulttimeout(None)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((ip, port))
            return True
        except OSError:
            return False


class PeerServer:
    """Handles incoming download requests from other peers."""

    def __init__(self, host, port, local_repository, client_repo_path):
        self.host = host
        self.port = port
        self.local_repository = local_repository
        self.client_repo_path = client_repo_path

    def handle_download_request(self, peer_connection, peer_address):
        """
        Handles a download request from another peer.
        This runs in a new thread for each download request.
        """
        try:
            message = peer_connection.recv(BUFFER_SIZE).decode('utf-8')
            parts = message.split()

            if parts[0].upper() == 'DOWNLOAD' and len(parts) == 2:
                file_name = parts[1]
                print(f"\n[PEER REQUEST] Received download request for '{file_name}' from {peer_address}")

                if file_name in self.local_repository:
                    file_path = self.local_repository[file_name]

                    if os.path.exists(file_path):
                        peer_connection.sendall(b'FILE_START')

                        with open(file_path, 'rb') as f:
                            while True:
                                bytes_read = f.read(BUFFER_SIZE)
                                if not bytes_read:
                                    break
                                peer_connection.sendall(bytes_read)

                        print(f"[PEER UPLOAD] Finished sending '{file_name}' to {peer_address}")
                    else:
                        peer_connection.sendall(b'FILE_ERROR')
                        print(f"[PEER UPLOAD] Error: File path not found: {file_path}")
                else:
                    peer_connection.sendall(b'FILE_NOT_FOUND')
                    print(f"[PEER UPLOAD] Error: File not in repository: {file_name}")
            
            elif parts[0].upper() == 'PING':
                print(f"\n[PEER REQUEST] Received PING from {peer_address}")
                peer_connection.sendall(b'PONG')
                time.sleep(0.1)
            
            elif parts[0].upper() == 'DISCOVER':
                print(f"\n[PEER REQUEST] Received DISCOVER from {peer_address}")
                response_bytes = b'' 
                if not self.local_repository:
                    response_bytes = b'DISCOVER_NO_FILES'
                else:
                    # Send a list of file names, separated by newlines
                    files = '\n'.join(self.local_repository.keys())
                    response = f"DISCOVER_OK\n{files}"
                    response_bytes = response.encode('utf-8')
                
                peer_connection.sendall(response_bytes)
                time.sleep(0.1) 
            else:
                peer_connection.sendall(b'PEER_UNKNOWN_COMMAND')
        except Exception as e:
            print(f"\n[PEER ERROR] Error handling peer {peer_address}: {e}")
        finally:
            peer_connection.close()

    def run(self):
        """
        Runs the server part of the client to listen for download requests
        from other peers. This must run in a separate thread. 
        """
        while True:
            peer_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                peer_server_socket.bind((self.host, self.port))
                peer_server_socket.listen(5)
                print(f"[PEER SERVER] Listening for other peers on {self.host}:{self.port}")

                while True:
                    peer_connection, peer_address = peer_server_socket.accept()
                    download_thread = threading.Thread(
                        target=self.handle_download_request,
                        args=(peer_connection, peer_address)
                    )
                    download_thread.daemon = True
                    download_thread.start()

            except OSError as e:
                print(f"\n[PEER SERVER ERROR] Could not bind to port {self.port}. Is another client using it? {e}")
                try:
                    new_port = input("Enter a new peer port to try again: ").strip()
                    if new_port.isdigit():
                        self.port = int(new_port)
                        print(f"[PEER SERVER] Retrying on port {self.port}...")
                        continue  
                    else:
                        print("[PEER SERVER] Invalid port input. Exiting peer server.")
                        break
                except KeyboardInterrupt:
                    print("\n[PEER SERVER] Exiting peer server.")
                    break
            except KeyboardInterrupt:
                pass
            finally:
                peer_server_socket.close()
            break


class FileDownloader:
    """Handles downloading files from other peers."""

    def __init__(self, client_repo_path, local_repository):
        self.client_repo_path = client_repo_path
        self.local_repository = local_repository

    def download_file_from_peer(self, file_name, peer_address_str):
        """
        Connects to a peer to download a file.
        This runs in a new thread for each download.
        """
        peer_socket = None
        try:
            peer_ip, peer_port = peer_address_str.split(':')
            peer_port = int(peer_port)

            print(f"\n[DOWNLOAD] Attempting to download '{file_name}' from {peer_ip}:{peer_port}")

            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            peer_socket.connect((peer_ip, peer_port))

            peer_socket.sendall(f"DOWNLOAD {file_name}".encode('utf-8'))

            if not os.path.exists(self.client_repo_path):
                os.makedirs(self.client_repo_path)

            save_path = os.path.join(self.client_repo_path, file_name)
            initial_response = peer_socket.recv(BUFFER_SIZE)

            if initial_response.startswith(b'FILE_START'):
                first_chunk = initial_response[len(b'FILE_START'):]
                with open(save_path, 'wb') as f:
                    if first_chunk:
                        f.write(first_chunk)
                    while True:
                        bytes_read = peer_socket.recv(BUFFER_SIZE)
                        if not bytes_read:
                            break
                        f.write(bytes_read)

                print(f"\n[DOWNLOAD] Successfully downloaded '{file_name}' and saved to {save_path}")
                self.local_repository[file_name] = save_path
                print(f"[PUBLISH] '{file_name}' is now available from this peer.")

            elif initial_response == b'FILE_NOT_FOUND':
                print(f"\n[DOWNLOAD ERROR] Peer {peer_ip}:{peer_port} does not have '{file_name}'.")
            elif initial_response == b'FILE_ERROR':
                print(f"\n[DOWNLOAD ERROR] Peer {peer_ip}:{peer_port} reported a file error (e.g., path not found).")
            else:
                print(f"\n[DOWNLOAD ERROR] Peer {peer_ip}:{peer_port} reported an unknown error or bad response.")

        except Exception as e:
            print(f"\n[DOWNLOAD ERROR] Failed to download from {peer_address_str}: {e}")
        finally:
            if peer_socket:
                peer_socket.close()


class P2PClient:
    """Main P2P client that interacts with the central server and manages user commands."""

    def __init__(self, server_host, server_port, peer_port, client_repo_path):
        self.server_host = server_host
        self.server_port = server_port
        self.peer_port = peer_port
        self.client_repo_path = client_repo_path
        self.local_repository = local_repository

    def monitor_network(self):
        """Continuously monitor internet connection, auto-shutdown if lost."""
        while True:
            if not NetworkHandler.check_network_connection():
                print("\n[NETWORK ERROR] Lost internet connection. Shutting down client.")
                os._exit(1)
            time.sleep(5)
    def ping_peer(self, peer_address_str):
        """Attempts to PING a peer directly."""
        peer_socket = None
        try:
            # Assumes peer_address_str is "ip:port"
            peer_ip, peer_port_str = peer_address_str.split(':')
            peer_port = int(peer_port_str)
            
            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            peer_socket.settimeout(3.0) 
            
            print(f"[PING] Pinging {peer_address_str}...")
            peer_socket.connect((peer_ip, peer_port))
            peer_socket.sendall(b'PING')
            
            response = peer_socket.recv(BUFFER_SIZE)
            if response == b'PONG':
                print(f"[PING] SUCCESS: {peer_address_str} is ALIVE.")
            else:
                print(f"[PING] FAILED: Peer sent unexpected response: {response.decode('utf-8')}")
                
        except socket.timeout:
            print(f"[PING] FAILED: {peer_address_str} is OFFLINE (timeout).")
        except ConnectionRefusedError:
            print(f"[PING] FAILED: {peer_address_str} is OFFLINE (connection refused).")
        except Exception as e:
            print(f"[PING] ERROR: {e}")
        finally:
            if peer_socket:
                peer_socket.close()
    
    def discover_peer(self, peer_address_str):
        """Attempts to DISCOVER the file list from a peer directly."""
        peer_socket = None
        try:
            peer_ip, peer_port_str = peer_address_str.split(':')
            peer_port = int(peer_port_str)
            
            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            peer_socket.settimeout(5.0) # 5 second timeout
            
            print(f"[DISCOVER] Requesting file list from {peer_address_str}...")
            peer_socket.connect((peer_ip, peer_port))
            peer_socket.sendall(b'DISCOVER')
            
            # Receive the full response. The peer will close the connection when done.
            full_response = b''
            while True:
                chunk = peer_socket.recv(BUFFER_SIZE)
                if not chunk:
                    break
                full_response += chunk
            
            response = full_response.decode('utf-8')

            if response == 'DISCOVER_NO_FILES':
                print(f"[DISCOVER] Peer {peer_address_str} has no files.")
            elif response.startswith('DISCOVER_OK\n'):
                files_list = response.split('\n', 1)[1]
                print(f"[DISCOVER] Files from {peer_address_str}:\n---")
                print(files_list)
                print("---")
            else:
                print(f"[DISCOVER] FAILED: Peer sent unexpected response: '{response}'")
                
        except socket.timeout:
            print(f"[DISCOVER] FAILED: {peer_address_str} is OFFLINE (timeout).")
        except ConnectionRefusedError:
            print(f"[DISCOVER] FAILED: {peer_address_str} is OFFLINE (connection refused).")
        except Exception as e:
            print(f"[DISCOVER] ERROR: {e}")
        finally:
            if peer_socket:
                peer_socket.close()
                
    def run_shell(self):
        """
        Main client function. Runs the user command shell 
        and connects to the central index server.
        """
        monitor_thread = threading.Thread(target=self.monitor_network, daemon=True)
        monitor_thread.start()
        if not os.path.exists(self.client_repo_path):
            os.makedirs(self.client_repo_path)
            print(f"Created repository directory: {self.client_repo_path}")

        
        peer_server = PeerServer(self.server_host, self.peer_port, self.local_repository, self.client_repo_path)
        peer_thread = threading.Thread(target=peer_server.run, daemon=True)
        peer_thread.start()
        
        downloader = FileDownloader(self.client_repo_path, self.local_repository)

        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.connect((self.server_host, self.server_port))
            print(f"Connected to index server at {self.server_host}:{self.server_port}")
        except ConnectionRefusedError:
            print(f"[ERROR] Could not connect to server at {self.server_host}:{self.server_port}.")
            print("Please ensure the server is running.")
            return
        except Exception as e:
            print(f"[ERROR] {e}")
            return
        
        input_queue = queue.Queue()

        def input_thread(q):
            while True:
                q.put(input("client> ").strip())

        threading.Thread(target=input_thread, args=(input_queue,), daemon=True).start()

        try:
            while True:
                if not NetworkHandler.check_network_connection():
                    print("[NETWORK ERROR] Lost connection. Exiting client.")
                    break
                try: 
                    command_line = input_queue.get_nowait()
                except queue.Empty:
                    time.sleep(0.1)
                    continue

                if not command_line:
                    continue
                parts = command_line.split()
                command = parts[0].lower()

                if command == 'publish' and len(parts) >= 2:
                    file_names = parts[1:]
                    for file_name in file_names:
                        local_name = file_name
                        full_local_path = os.path.join(self.client_repo_path, local_name)

                        if not os.path.exists(full_local_path):
                            print(f"[ERROR] Local file not found: {full_local_path}")
                            continue

                        self.local_repository[file_name] = full_local_path
                        message = f"PUBLISH {file_name} {self.peer_port}"
                        server_socket.sendall(message.encode('utf-8'))
                        response = server_socket.recv(BUFFER_SIZE).decode('utf-8')

                        if response == 'PUBLISH_OK':
                            print(f"[PUBLISH] Successfully published '{file_name}'")
                        else:
                            print(f"[PUBLISH] Server error for '{file_name}': {response}")

                elif command == 'fetch' and len(parts) >= 2:
                    file_names = parts[1:]
                    for file_name in file_names:
                        message = f"FETCH {file_name}"
                        server_socket.sendall(message.encode('utf-8'))
                        response = server_socket.recv(BUFFER_SIZE).decode('utf-8')

                        if response == 'FETCH_NOT_FOUND':
                            print(f"[FETCH] File '{file_name}' not found on the network.")
                        elif response.startswith('PEERS '):
                            peer_list_str = response.split(' ', 1)[1]
                            peer_addresses = peer_list_str.split()

                            if not peer_addresses:
                                print(f"[FETCH] Server found file '{file_name}' but no peers are online.")
                                continue

                            selected_peer = peer_addresses[0]
                            download_thread = threading.Thread(
                                target=downloader.download_file_from_peer,
                                args=(file_name, selected_peer),
                                daemon=True
                            )
                            download_thread.start()
                            download_thread.join()
                        elif response.startswith('ERROR'):
                            print(f"[FETCH] Unexpected server response: {response}")
                        else:
                            print(f"[FETCH] Received unknown response from server: {response}")

                elif command == 'list':
                    server_socket.sendall(b'LIST')
                    response = server_socket.recv(BUFFER_SIZE).decode('utf-8')
                    if response == 'NO_FILES':
                        print("[LIST] No files published yet.")
                    else:
                        print("[LIST] Files on server:\n" + response)
                        
                elif command == 'ping' and len(parts) == 2:
                    peer_address_str = parts[1]
                    ping_thread = threading.Thread(target=self.ping_peer, args=(peer_address_str,), daemon=True)
                    ping_thread.start()
                    
                elif command == 'discover' and len(parts) == 2:
                    peer_address_str = parts[1]
                    discover_thread = threading.Thread(target=self.discover_peer, args=(peer_address_str,), daemon=True)
                    discover_thread.start()
                
                
                elif command == 'unpublish' and len(parts) >= 2:
                    file_names = parts[1:]
                    for file_name in file_names:
                        message = f"UNPUBLISH {file_name} {self.peer_port}"
                        server_socket.sendall(message.encode('utf-8'))
                        response = server_socket.recv(BUFFER_SIZE).decode('utf-8')
                        if response == 'UNPUBLISH_OK':
                            print(f"[UNPUBLISH] Removed '{file_name}' from server index.")
                            self.local_repository.pop(file_name, None)
                        elif response == 'UNPUBLISH_NOT_FOUND':
                            print(f"[UNPUBLISH] File '{file_name}' not found on server.")
                        else:
                            print(f"[UNPUBLISH] Unexpected response: {response}")

                elif command == 'exit':
                    print("Exiting client.")
                    break

                else:
                    print("Unknown command. Available commands:")
                    print("publish <file_name>")
                    print("unpublish <file_name>")
                    print("fetch <file_name>")
                    print("list")
                    print("ping <ip:port>")
                    print("discover <ip:port>")
                    print("exit")

        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Client is shutting down.")
        finally:
            server_socket.close()

def safe_input(prompt):
    if not NetworkHandler.check_network_connection():
        print("[ERROR] Network disconnected. Exiting client.")
        os._exit(1)
    return input(prompt)

if __name__ == "__main__":
    print("=== P2P Client ===")

    if not NetworkHandler.check_network_connection():
        print("[ERROR] No network connection detected. Client cannot start.")
        exit(1)

    host_input = safe_input(f"Enter server IP (default {SERVER_HOST}): ").strip()
    SERVER_HOST = host_input if host_input else SERVER_HOST

    port_input = safe_input(f"Enter server port (default {SERVER_PORT}): ").strip()
    try:
        SERVER_PORT = int(port_input) if port_input else SERVER_PORT
    except ValueError:
        print(f"[WARN] Invalid port input. Using default {SERVER_PORT}.")

    peer_input = safe_input(f"Enter peer port to listen on (default {PEER_PORT}): ").strip()
    try:
        if peer_input:
            PEER_PORT = int(peer_input)
    except ValueError:
        print(f"[WARN] Invalid peer port input. Using default {PEER_PORT}.")

    CLIENT_REPO_PATH = f'client_{PEER_PORT}_files'

    if not NetworkHandler.check_network_connection():
        print("[ERROR] Network disconnected. Cannot start client.")
        exit(1)

    client = P2PClient(SERVER_HOST, SERVER_PORT, PEER_PORT, CLIENT_REPO_PATH)
    client.run_shell()
