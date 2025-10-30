# client.py
# P2P Client (Peer)

import socket
import threading
import os

# --- CLIENT CONFIGURATION ---
# Central Index Server details
SERVER_HOST = '127.0.0.1' # Change to server's IP if not on same machine
SERVER_PORT = 9000

# This client's details
# Must be unique for each client running on the same machine
PEER_PORT = 9001 # Port this client will listen on for other peers
CLIENT_REPO_PATH = 'client_files' # Directory to store local files

# In-memory mapping of this client's files
# maps: file_name -> local_file_path (lname)
local_repository = {}
# -----------------------------

BUFFER_SIZE = 1024

def handle_download_request(peer_connection, peer_address):
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
            
            # Check if we have this file in our local repository
            if file_name in local_repository:
                file_path = local_repository[file_name]
                
                if os.path.exists(file_path):
                    # Send the file data
                    peer_connection.sendall(b'FILE_START')
                    
                    with open(file_path, 'rb') as f:
                        while True:
                            bytes_read = f.read(BUFFER_SIZE)
                            if not bytes_read:
                                break # End of file
                            peer_connection.sendall(bytes_read)
                            
                    print(f"[PEER UPLOAD] Finished sending '{file_name}' to {peer_address}")
                else:
                    peer_connection.sendall(b'FILE_ERROR')
                    print(f"[PEER UPLOAD] Error: File path not found: {file_path}")
            else:
                peer_connection.sendall(b'FILE_NOT_FOUND')
                print(f"[PEER UPLOAD] Error: File not in repository: {file_name}")
                
    except Exception as e:
        print(f"\n[PEER ERROR] Error handling peer {peer_address}: {e}")
    finally:
        peer_connection.close()

def run_peer_server(host, port):
    """
    Runs the server part of the client to listen for download requests
    from other peers. This must run in a separate thread. 
    """
    peer_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        peer_server_socket.bind((host, port))
        peer_server_socket.listen(5)
        print(f"[PEER SERVER] Listening for other peers on {host}:{port}")
        
        while True:
            peer_connection, peer_address = peer_server_socket.accept()
            # Start a new thread to handle the download request
            download_thread = threading.Thread(
                target=handle_download_request,
                args=(peer_connection, peer_address)
            )
            download_thread.daemon = True
            download_thread.start()
            
    except OSError as e:
        print(f"\n[PEER SERVER ERROR] Could not bind to port {port}. Is another client using it? {e}")
    except KeyboardInterrupt:
        pass # Will be handled by main thread
    finally:
        peer_server_socket.close()

def download_file_from_peer(file_name, peer_address_str):
    """
    Connects to a peer to download a file. [cite: 12]
    This runs in a new thread for each download.
    """
    try:
        peer_ip, peer_port = peer_address_str.split(':')
        peer_port = int(peer_port)
        
        print(f"\n[DOWNLOAD] Attempting to download '{file_name}' from {peer_ip}:{peer_port}")
        
        peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        peer_socket.connect((peer_ip, peer_port))
        
        # 1. Send download request
        peer_socket.sendall(f"DOWNLOAD {file_name}".encode('utf-8'))
        
        # 2. Receive file data
        # Ensure the repository path exists
        if not os.path.exists(CLIENT_REPO_PATH):
            os.makedirs(CLIENT_REPO_PATH)
            
        save_path = os.path.join(CLIENT_REPO_PATH, file_name)
        
        # Check for initial response
        initial_response = peer_socket.recv(BUFFER_SIZE)
        
        if initial_response == b'FILE_START':
            with open(save_path, 'wb') as f:
                while True:
                    bytes_read = peer_socket.recv(BUFFER_SIZE)
                    if not bytes_read:
                        break # Download complete
                    f.write(bytes_read)
            
            print(f"\n[DOWNLOAD] Successfully downloaded '{file_name}' and saved to {save_path}")
            # Automatically publish this new file
            # Note: This requires the server_socket to be accessible.
            # For simplicity, we'll just add it locally.
            # You would need to send a 'PUBLISH' message to the server here.
            local_repository[file_name] = save_path
            print(f"[PUBLISH] '{file_name}' is now available from this peer.")
            
        elif initial_response == b'FILE_NOT_FOUND':
            print(f"\n[DOWNLOAD ERROR] Peer {peer_ip}:{peer_port} does not have '{file_name}'.")
        else:
            print(f"\n[DOWNLOAD ERROR] Peer {peer_ip}:{peer_port} reported an error.")
            
    except Exception as e:
        print(f"\n[DOWNLOAD ERROR] Failed to download from {peer_address_str}: {e}")
    finally:
        peer_socket.close()


def run_client_shell():
    """
    Main client function. Runs the user command shell 
    and connects to the central index server.
    """
    # Ensure the local repository directory exists
    if not os.path.exists(CLIENT_REPO_PATH):
        os.makedirs(CLIENT_REPO_PATH)
        print(f"Created repository directory: {CLIENT_REPO_PATH}")
    
    # --- Start the Peer Server Thread ---
    # This thread will listen for download requests from other peers
    peer_server_thread = threading.Thread(
        target=run_peer_server,
        args=('0.0.0.0', PEER_PORT),
        daemon=True
    )
    peer_server_thread.start()

    # --- Connect to the Central Index Server ---
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.connect((SERVER_HOST, SERVER_PORT))
        print(f"Connected to index server at {SERVER_HOST}:{SERVER_PORT}")
    except ConnectionRefusedError:
        print(f"[ERROR] Could not connect to server at {SERVER_HOST}:{SERVER_PORT}.")
        print("Please ensure the server is running.")
        return
    except Exception as e:
        print(f"[ERROR] {e}")
        return

    # --- Main Command Loop ---
    try:
        while True:
            # The prompt format `> ` is simple
            command_line = input("client> ").strip()
            if not command_line:
                continue

            parts = command_line.split()
            command = parts[0].lower()

            if command == 'publish' and len(parts) >= 2:
                # Có thể publish 1 hoặc nhiều file
                file_names = parts[1:]
                for file_name in file_names:
                    local_name = file_name  # dùng luôn tên file làm local_name
                    full_local_path = os.path.join(CLIENT_REPO_PATH, local_name)

                    if not os.path.exists(full_local_path):
                        print(f"[ERROR] Local file not found: {full_local_path}")
                        continue

                    # 1. Thêm vào local repo
                    local_repository[file_name] = full_local_path

                    # 2. Gửi PUBLISH message
                    message = f"PUBLISH {file_name} {PEER_PORT}"
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
                            target=download_file_from_peer,
                            args=(file_name, selected_peer),
                            daemon=True
                        )
                        download_thread.start()
                        download_thread.join()  
                    else:
                        print(f"[FETCH] Received unknown response from server: {response}")


            elif command == 'exit':
                print("Exiting client.")
                break
            
            else:
                print("Unknown command. Available commands:")
                print("publish <local_name> <file_name>")
                print("fetch <file_name>")
                print("exit")

    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Client is shutting down.")
    finally:
        server_socket.close()

if __name__ == "__main__":
    # Ask user for a unique port for the peer server
    # This is important if running multiple clients on one machine
    try:
        port_input = input(f"Enter peer port to listen on (default {PEER_PORT}): ")
        if port_input:
            PEER_PORT = int(port_input)
    except ValueError:
        print(f"Invalid port. Using default {PEER_PORT}.")
    
    # Set the repo path to be unique for this port
    CLIENT_REPO_PATH = f'client_{PEER_PORT}_files'
    
    run_client_shell()