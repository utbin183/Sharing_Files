# server.py
# Centralized Index Server for P2P File Sharing

import socket
import threading

# Server configuration
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 9000
BUFFER_SIZE = 1024

# Global data structures to track clients and files
# file_index maps: file_name -> set of (ip, port) tuples
file_index = {}
# client_lock is a mutex to protect access to the file_index
client_lock = threading.Lock()
def check_network_connection(ip="8.8.8.8", port=53):
    try:
        socket.setdefaulttimeout(None)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((ip, port))
        return True
    except OSError:
        return False
def handle_client_connection(client_socket, client_address):
    """
    Handles an individual client connection in a separate thread.
    """
    print(f"[NEW CONNECTION] {client_address} connected.")
    
    try:
        while True:
            # Receive message from client
            message = client_socket.recv(BUFFER_SIZE).decode('utf-8')
            if not message:
                break # Client disconnected
                
            print(f"[REQUEST] Received from {client_address}: {message}")
            parts = message.split()
            if not parts:
                continue
            command = parts[0].upper()

            if command == 'PUBLISH' and len(parts) == 3:
                # Client wants to publish a file
                # Format: PUBLISH <file_name> <peer_port>
                file_name = parts[1]
                peer_port = int(parts[2])
                peer_address = (client_address[0], peer_port) # Use client's IP
                
                # Use lock to safely modify the shared file_index
                with client_lock:
                    if file_name not in file_index:
                        file_index[file_name] = set()
                    file_index[file_name].add(peer_address)
                
                print(f"[PUBLISH] Peer {peer_address} added file: {file_name}")
                client_socket.sendall(b'PUBLISH_OK')
            
            elif command == 'UNPUBLISH' and len(parts) == 3:
                file_name = parts[1]
                peer_port = int(parts[2])
                peer_address = (client_address[0], peer_port)
                with client_lock:
                    if file_name in file_index and peer_address in file_index[file_name]:
                        file_index[file_name].remove(peer_address)
                        if not file_index[file_name]:
                            del file_index[file_name]
                        print(f"[UNPUBLISH] {peer_address} removed {file_name}")
                        client_socket.sendall(b'UNPUBLISH_OK')
                    else:
                        client_socket.sendall(b'UNPUBLISH_NOT_FOUND')

            elif command == 'FETCH' and len(parts) == 2:
                # Client wants to fetch a file
                # Format: FETCH <file_name>
                file_name = parts[1]
                
                # Find peers that have the file
                peer_list = []
                with client_lock:
                    if file_name in file_index:
                        peer_list = list(file_index[file_name])
                
                if not peer_list:
                    # No peers found
                    print(f"[FETCH] File not found: {file_name}")
                    client_socket.sendall(b'FETCH_NOT_FOUND')
                else:
                    # Send the list of peers back to the client
                    # Format: PEERS <ip1:port1> <ip2:port2> ...
                    response = 'PEERS ' + ' '.join([f"{ip}:{port}" for ip, port in peer_list])
                    print(f"[FETCH] Sending peers for {file_name}: {response}")
                    client_socket.sendall(response.encode('utf-8'))
            
            elif command == 'PEERS' and len(parts) == 2:
                file_name = parts[1]
                with client_lock:
                    if file_name in file_index:
                        peers = file_index[file_name]
                        response = '\n'.join([f"{ip}:{port}" for ip, port in peers])
                        client_socket.sendall(response.encode('utf-8'))
                    else:
                        client_socket.sendall(b'NO_PEERS')
                        
            elif command == 'LIST':
                with client_lock:
                    if not file_index:
                        client_socket.sendall(b'NO_FILES')
                    else:
                        response_lines = []
                        for file_name, peers in file_index.items():
                            peer_str = ', '.join([f"{ip}:{port}" for ip, port in peers])
                            response_lines.append(f"{file_name} -> {peer_str}")
                        response = '\n'.join(response_lines)
                        client_socket.sendall(response.encode('utf-8'))

            else:
                # Unknown command
                client_socket.sendall(b'UNKNOWN_COMMAND')

    except ConnectionResetError:
        print(f"[DISCONNECTED] Client {client_address} disconnected abruptly.")
    except Exception as e:
        print(f"[ERROR] Error handling client {client_address}: {e}")
    finally:
        print(f"[CLOSED] Connection from {client_address} closed.")
        client_socket.close()

def run_server(host, port):
    """
    Main server function to listen for and accept new connections.
    """
    while True:
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.bind((host, port))
            server_socket.listen(5)
            print(f"[LISTENING] Server listening on {host}:{port}")
            break
        except OSError as e:
            print(f"[ERROR] Cannot bind to {host}:{port} — {e}")
            try:
                new_port = input("Enter a new port number to retry: ").strip()
                port = int(new_port)
            except ValueError:
                print("Invalid input. Using default port 9000.")
                port = DEFAULT_PORT
    try:
        while True:
            # Accept a new connection
            client_socket, client_address = server_socket.accept()
            
            # Create a new thread to handle this client
            # This allows the server to handle multiple clients concurrently
            client_thread = threading.Thread(
                target=handle_client_connection,
                args=(client_socket, client_address)
            )
            client_thread.daemon = True # Allows server to exit even if threads are running
            client_thread.start()
            
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Server is shutting down.")
    finally:
        server_socket.close()

if __name__ == "__main__":
    print("=== Centralized Index Server ===")

    if not check_network_connection():
        print("[ERROR] No network connection detected. Server cannot start.")
        exit(1)

    host_input = input(f"Enter host (default {DEFAULT_HOST}): ").strip() or DEFAULT_HOST
    try:
        port_input = int(input(f"Enter port (default {DEFAULT_PORT}): ").strip() or DEFAULT_PORT)
    except ValueError:
        port_input = DEFAULT_PORT

    run_server(host_input, port_input)
