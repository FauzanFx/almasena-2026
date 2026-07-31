# almasena-dev/ship_system/src/network/net_bridge.py

import socket
import json
import time
import sys

class NetBridge:
    def __init__(self, gcs_ip="100.81.234.32", udp_port=5006, listen_port=5005):
        self.gcs_address = (gcs_ip, udp_port)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', listen_port))
        self.sock.setblocking(False)
        print(f"[NET-BRIDGE] Pipa UDP aktif. Kirim ke GCS={gcs_ip}:{udp_port} | Mendengar di port={listen_port}")

    def transmit_ship_status(self, raw_sensor_data, vision_data):
        payload = {
            "timestamp": time.time(),
            "sensors": raw_sensor_data,
            "vision": vision_data
        }
        try:
            message = json.dumps(payload).encode('utf-8')
            self.sock.sendto(message, self.gcs_address)
        except Exception:
            pass

    def receive_commands(self):
        latest_data = None

        # DRAIN LOOP: Sedot dan buang perintah lama, ambil perintah paling baru
        while True:
            try:
                data, _ = self.sock.recvfrom(1024)
                latest_data = data
            except BlockingIOError:
                break
            except Exception:
                break

        if latest_data:
            try:
                commands = json.loads(latest_data.decode('utf-8'))

                if commands and isinstance(commands, dict):
                    log_msg = (
                        f"\r[NET-RX LIVE] "
                        f"Surge: {commands.get('surge', 0):4d} | "
                        f"Yaw: {commands.get('yaw', 0):4d} | "
                        f"Pitch: {commands.get('pitch', 0):4d} | "
                        f"Ballast: {commands.get('ballast_cmd', 0):2d} | "
                        f"Grip: {commands.get('gripper_cmd', 0):2d} | "
                        f"Kill-Cmd: {str(commands.get('kill_switch', False)):5s}"
                    )
                    sys.stdout.write(log_msg)
                    sys.stdout.flush()

                return commands
            except Exception:
                return None

        return None

    def close(self):
        self.sock.close()
        print("[NET-BRIDGE] Soket jaringan LAN resmi ditutup.")
