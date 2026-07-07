# almasena-dev/gcs_system/src/net_handler.py

import socket
import json

class NetHandler:
    def __init__(self, rov_ip="192.168.1.20", send_port=5005, recv_port=5006):
        self.rov_ip = rov_ip
        self.send_port = send_port
        self.recv_port = recv_port
        
        # Inisialisasi Soket UDP untuk Kirim Komando ke ROV
        self.sock_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Inisialisasi Soket UDP untuk Terima Telemetri dari ROV
        self.sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_recv.bind(("0.0.0.0", self.recv_port))
        self.sock_recv.setblocking(False) # Non-blocking supaya GUI Laptop lu gak freeze

    def send_commands_to_rov(self, command_dict):
        """
        Mengemas input joystick/tombol GCS menjadi JSON lalu menembakkannya ke ROV.
        """
        try:
            json_data = json.dumps(command_dict).encode('utf-8')
            self.sock_send.sendto(json_data, (self.rov_ip, self.send_port))
        except Exception as e:
            print(f"[GCS-NET] Gagal mengirim komando ke ROV: {e}")

    def receive_telemetry_from_rov(self):
        """
        Membaca paket telemetri sensor dan koordinat YOLOv8 dari lambung kapal.
        Mengembalikan data berupa dictionary jika sukses, atau None jika tidak ada data baru.
        """
        try:
            data, addr = self.sock_recv.recvfrom(4096)
            json_data = data.decode('utf-8')
            return json.loads(json_data)
        except BlockingIOError:
            # Tidak ada paket masuk pada detak loop saat ini (Kondisi normal pada non-blocking)
            return None
        except Exception as e:
            print(f"[GCS-NET] Error saat membaca telemetri: {e}")
            return None

    def close(self):
        """Menutup soket jaringan secara aman saat aplikasi GCS dimatikan"""
        self.sock_send.close()
        self.sock_recv.close()
        print("[GCS-NET] Soket jaringan GCS resmi ditutup.")
