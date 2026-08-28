# almasena-dev/ship_system/src/network/net_bridge.py

import socket
import json
import time

class NetBridge:
    def __init__(self, gcs_ip="192.168.1.15", udp_port=5006, listen_port=5005):
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
            self.sock.sendto(json.dumps(payload).encode('utf-8'), self.gcs_address)
        except Exception:
            pass

    def receive_commands(self):
        latest_data = None
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
                return json.loads(latest_data.decode('utf-8'))
            except Exception:
                return None
        return None

    def close(self):
        self.sock.close()
        print("\n[NET-BRIDGE] Soket jaringan LAN resmi ditutup.")
