import subprocess
import time
import os
import threading

# Paths (adjust if needed)
SERVER_PATH = "app/server.py"
CLIENT_PATH = "app/client.py"

# Configuration
SERVER_IP = "127.0.0.1"
SERVER_PORT = 9000
NUM_PEERS = 3
NUM_FILES = 10  # Number of files per peer for stress test
BASE_PEER_PORT = 9001

# Ensure client repo base exists
os.makedirs("stress_client_files", exist_ok=True)

# Utility to run a process
def run_process(cmd):
    return subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

# Prepare test files for each peer
peer_files = {}
for i in range(NUM_PEERS):
    peer_port = BASE_PEER_PORT + i
    peer_dir = f"stress_client_files/peer_{peer_port}"
    os.makedirs(peer_dir, exist_ok=True)
    files = []
    for j in range(1, NUM_FILES + 1):
        fname = f"file_{i+1}_{j}.txt"
        fpath = os.path.join(peer_dir, fname)
        with open(fpath, "w") as f:
            f.write(f"Peer {i+1}, File {j}\n" * 100)
        files.append(fname)
    peer_files[peer_port] = (peer_dir, files)

# Function to run a client and send commands
def run_client(peer_port, commands, repo_path):
    cmd = f"python {CLIENT_PATH}"
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Input server IP, server port, peer port, and repo path
    input_cmds = [
        f"{SERVER_IP}\n",
        f"{SERVER_PORT}\n",
        f"{peer_port}\n",
    ] + [c + "\n" for c in commands] + ["exit\n"]

    for line in input_cmds:
        proc.stdin.write(line)
        proc.stdin.flush()
        time.sleep(0.05)

    out, err = proc.communicate()
    return out, err

# Measure latency helper
def measure_latency(label, func):
    start = time.time()
    result = func()
    end = time.time()
    latency = end - start
    print(f"[{label}] Time taken: {latency:.4f}s")
    return latency, result

# Main stress test
def main():
    print("\n=== MULTI-PEER STRESS TEST ===\n")

    # Launch server
    print("[START] Launching central server...")
    server_proc = run_process(f"python {SERVER_PATH}")
    time.sleep(2)  # Allow server to start

    try:
        # Publish files concurrently
        print(f"\n[STRESS] Publishing files from {NUM_PEERS} peers...")
        publish_threads = []
        latencies_publish = {}

        def publish_task(peer_port, files, repo_path):
            latency, _ = measure_latency(f"PUBLISH_PEER_{peer_port}", lambda: run_client(peer_port, [f"publish {' '.join(files)}"], repo_path))
            latencies_publish[peer_port] = latency

        for peer_port, (repo_path, files) in peer_files.items():
            t = threading.Thread(target=publish_task, args=(peer_port, files, repo_path))
            t.start()
            publish_threads.append(t)

        for t in publish_threads:
            t.join()

        # List files on server (single client)
        print("\n[STRESS] Listing all files on server...")
        latency_list, output_list = measure_latency("LIST_ALL", lambda: run_client(BASE_PEER_PORT, ["list"], peer_files[BASE_PEER_PORT][0]))

        # Fetch files concurrently (each peer fetches files from other peers)
        print("\n[STRESS] Fetching files concurrently...")
        fetch_threads = []
        latencies_fetch = {}

        def fetch_task(peer_port, target_files):
            latency, _ = measure_latency(f"FETCH_PEER_{peer_port}", lambda: run_client(peer_port, [f"fetch {' '.join(target_files)}"], peer_files[peer_port][0]))
            latencies_fetch[peer_port] = latency

        # Assign files to fetch: each peer fetches all files from other peers
        for peer_port, (repo_path, _) in peer_files.items():
            other_files = []
            for other_port, (_, files) in peer_files.items():
                if other_port != peer_port:
                    other_files.extend(files)
            t = threading.Thread(target=fetch_task, args=(peer_port, other_files))
            t.start()
            fetch_threads.append(t)

        for t in fetch_threads:
            t.join()

        # Unpublish files concurrently
        print("\n[STRESS] Unpublishing files from all peers...")
        unpublish_threads = []
        latencies_unpublish = {}

        def unpublish_task(peer_port, files, repo_path):
            latency, _ = measure_latency(f"UNPUBLISH_PEER_{peer_port}", lambda: run_client(peer_port, [f"unpublish {' '.join(files)}"], repo_path))
            latencies_unpublish[peer_port] = latency

        for peer_port, (repo_path, files) in peer_files.items():
            t = threading.Thread(target=unpublish_task, args=(peer_port, files, repo_path))
            t.start()
            unpublish_threads.append(t)

        for t in unpublish_threads:
            t.join()

        # Summary
        print("\n=== STRESS TEST RESULTS ===")
        print(f"{'Operation':<20}{'Peer':<10}{'Latency (s)':<15}")
        print("-"*45)
        for peer_port, latency in latencies_publish.items():
            print(f"{'PUBLISH':<20}{peer_port:<10}{latency:<15.4f}")
        print(f"{'LIST_ALL':<20}{'-':<10}{latency_list:<15.4f}")
        for peer_port, latency in latencies_fetch.items():
            print(f"{'FETCH':<20}{peer_port:<10}{latency:<15.4f}")
        for peer_port, latency in latencies_unpublish.items():
            print(f"{'UNPUBLISH':<20}{peer_port:<10}{latency:<15.4f}")

    finally:
        print("\n[SHUTDOWN] Terminating server...")
        server_proc.terminate()

if __name__ == "__main__":
    main()
