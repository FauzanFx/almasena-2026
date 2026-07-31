# almasena-dev/gcs_system/src/net_handler.py

import socket
import json

class NetHandler:
    def __init__(self, rov_ip="100.64.105.25", send_port=5005, recv_port=5006):
        self.rov_ip = rov_ip
        self.send_port = send_port
        self.recv_port = recv_port

        self.sock_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_recv.bind(("0.0.0.0", self.recv_port))
        self.sock_recv.setblocking(False)

    def send_commands_to_rov(self, command_dict):
        try:
            json_data = json.dumps(command_dict).encode('utf-8')
            self.sock_send.sendto(json_data, (self.rov_ip, self.send_port))
        except Exception as e:
            print(f"[GCS-NET] Gagal kirim command: {e}")

    def receive_telemetry_from_rov(self):
        latest_data = None

        # Drain Buffer: Kuras semua paket lama di memori, ambil paket paling baru
        while True:
            try:
                data, _ = self.sock_recv.recvfrom(65535)
                latest_data = data
            except BlockingIOError:
                break
            except Exception as e:
                print(f"[GCS-NET] Error recv buffer: {e}")
                break

        if latest_data:
            try:
                return json.loads(latest_data.decode('utf-8'))
            except Exception:
                return None

        return None

    def close(self):
        self.sock_send.close()
        self.sock_recv.close()
        print("[GCS-NET] Soket jaringan GCS resmi ditutup.")
