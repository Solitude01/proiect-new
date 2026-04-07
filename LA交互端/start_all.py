"""
LA IIoT Multi-Service Launcher
Starts both console service (port 8000) and business view service (port 6010)
in a single command using subprocess.
"""

import subprocess
import sys
import time
import signal
import os

def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║           LA IIoT Multi-Service Launcher                     ║
╠══════════════════════════════════════════════════════════════╣
║  Console Service:  http://0.0.0.0:8000                       ║
║  Business Service: http://0.0.0.0:6010                       ║
╚══════════════════════════════════════════════════════════════╝
""")

    processes = []

    def signal_handler(sig, frame):
        print("\n\n[Shutdown] Stopping all services...")
        for p in processes:
            if p.poll() is None:
                p.terminate()
        time.sleep(1)
        for p in processes:
            if p.poll() is None:
                p.kill()
        print("[Shutdown] All services stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        # Start business view service on port 6010
        print("[1/2] Starting business view service on port 6010...")
        p1 = subprocess.Popen([
            sys.executable, "-m", "uvicorn",
            "main:app",
            "--host", "0.0.0.0",
            "--port", "6010",
            "--ws-ping-interval", "20",
            "--ws-ping-timeout", "10"
        ])
        processes.append(p1)

        time.sleep(2)

        # Start console service on port 8000
        print("[2/2] Starting console service on port 8000...")
        p2 = subprocess.Popen([
            sys.executable, "-m", "uvicorn",
            "main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--ws-ping-interval", "20",
            "--ws-ping-timeout", "10"
        ])
        processes.append(p2)

        print("\n[OK] Both services started!")
        print("  - Console:  http://localhost:8000")
        print("  - Business: http://localhost:6010")
        print("\nPress Ctrl+C to stop\n")

        # Wait for all processes
        while True:
            for p in processes:
                ret = p.poll()
                if ret is not None and ret != 0:
                    print(f"[Error] A service exited with code {ret}")
                    signal_handler(None, None)
            time.sleep(1)

    except Exception as e:
        print(f"[Error] {e}")
        signal_handler(None, None)

if __name__ == "__main__":
    main()
