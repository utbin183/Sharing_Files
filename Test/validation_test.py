import subprocess
import time
import os

SERVER_IP = "127.0.0.1"
SERVER_PORT = 9000
PEER_PORTS = [9001, 9002]
TEST_FILE = "validation_demo.txt"

# --- Setup: create a folder and test file for each peer ---
for port in PEER_PORTS:
    folder = f"client_{port}_files"
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, TEST_FILE), "w") as f:
        f.write("Validation test file content.\n" * 100)

def run_server():
    print("[START] Launching server...")
    proc = subprocess.Popen(
        ["python", "App/server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    # Auto input host and port
    proc.stdin.write("0.0.0.0\n")
    proc.stdin.write(f"{SERVER_PORT}\n")
    proc.stdin.flush()
    time.sleep(1.5)
    print("[SERVER] Running on 0.0.0.0:9000")
    return proc

def run_client(peer_port, commands, hold=False):
    """Run a client. If hold=True, the client keeps running (so peer1 maintains connection)."""
    print(f"\n[CLIENT {peer_port}] Starting...")
    proc = subprocess.Popen(
        ["python", "App/client.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Send server IP and port, then peer port and commands
    inputs = [
        f"{SERVER_IP}\n",
        f"{SERVER_PORT}\n",
        f"{peer_port}\n"
    ] + [cmd + "\n" for cmd in commands]

    if not hold:
        inputs.append("exit\n")  # Exit automatically if hold is False

    for line in inputs:
        proc.stdin.write(line)
        proc.stdin.flush()
        time.sleep(0.3)

    if hold:
        return proc  # Keep the peer running
    else:
        out, err = proc.communicate(timeout=15)
        if err.strip():
            print(f"[ERROR {peer_port}] {err.strip()}")
        print(out)
        return out

def check_contains(output, keyword, step_name):
    """Check if the keyword appears in the client output."""
    if keyword.lower() in output.lower():
        print(f"[PASS] {step_name}")
        return True
    else:
        print(f"[FAIL] {step_name}")
        return False

def main():
    print("\n=== SANITY VALIDATION TEST (Auto Input Mode) ===\n")

    server_proc = run_server()

    try:
        # Start peer1 and keep it running so peer2 can fetch files
        peer1_proc = run_client(PEER_PORTS[0], [f"publish {TEST_FILE}"], hold=True)
        time.sleep(3)  # Allow server to update its file index

        # Peer1 lists its files
        out_list1 = run_client(PEER_PORTS[0], ["list"])
        check_contains(out_list1, TEST_FILE, "List operation")

        # Peer2 fetches the file from peer1
        time.sleep(2)
        out_fetch = run_client(PEER_PORTS[1], [f"fetch {TEST_FILE}"])
        check_contains(out_fetch, "downloaded", "Fetch operation")

        # Peer1 unpublishes the file
        out_unpub = run_client(PEER_PORTS[0], [f"unpublish {TEST_FILE}"])
        check_contains(out_unpub, "removed", "Unpublish operation")

        # Check that the file has been removed from the index
        out_list2 = run_client(PEER_PORTS[0], ["list"])
        if TEST_FILE not in out_list2:
            print("[PASS] File removed successfully from list.")
        else:
            print("[FAIL] File still appears after unpublish.")

        print("\n=== VALIDATION TEST COMPLETED ===")

    finally:
        print("\n[SHUTDOWN] Terminating server & peer...")
        try:
            peer1_proc.terminate()
        except Exception:
            pass
        server_proc.terminate()
        time.sleep(1)

if __name__ == "__main__":
    main()
