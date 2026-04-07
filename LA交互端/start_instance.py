"""
Single-Instance Launcher
Starts the middleware service for a specific instance on a dedicated port.

Usage:
    python start_instance.py <instance_id> <port>

Example:
    python start_instance.py line1 8001
    python start_instance.py line2 8002
"""

import sys
import os
import subprocess


def main():
    if len(sys.argv) != 3:
        print("Usage: python start_instance.py <instance_id> <port>")
        print("Example: python start_instance.py line1 8001")
        sys.exit(1)

    instance_id = sys.argv[1]
    port = sys.argv[2]

    # Validate port
    try:
        port_num = int(port)
        if not (1 <= port_num <= 65535):
            raise ValueError("Port out of range")
    except ValueError:
        print(f"Error: Invalid port number: {port}")
        sys.exit(1)

    # Set environment variables for single-instance mode
    env = os.environ.copy()
    env["INSTANCE_ID"] = instance_id
    env["PORT"] = port

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           LA IIoT Single-Instance Service                    ║
╠══════════════════════════════════════════════════════════════╣
║  Instance ID: {instance_id:<46} ║
║  Port:        {port:<46} ║
║  URL:         http://localhost:{port}{' ' * (26 - len(port))} ║
╚══════════════════════════════════════════════════════════════╝
    """)

    # Start uvicorn with the specified configuration
    cmd = [
        sys.executable, "-m", "uvicorn",
        "main:app",
        "--host", "0.0.0.0",
        "--port", port,
        "--ws-ping-interval", "20",
        "--ws-ping-timeout", "10",
        "--reload" if env.get("RELOAD", "").lower() == "true" else ""
    ]

    # Remove empty string if reload is not set
    cmd = [c for c in cmd if c]

    try:
        subprocess.run(cmd, env=env)
    except KeyboardInterrupt:
        print("\n[Shutdown] Service stopped by user")
    except Exception as e:
        print(f"[Error] Failed to start service: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
