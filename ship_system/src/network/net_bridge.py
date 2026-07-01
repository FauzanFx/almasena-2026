# almasena-dev/ship_system/src/network/net_bridge.py

import socket
import json
import time

class NetBridge:
    def __init__(self, gcs_ip="192.168.1.10", udp_port=14550):
        self.gcs_address = (gcs_ip, udp_port)
        
        # Inisialisasi soket UDP lokal untuk media komunikasi Ethernet
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Mengatur soket ke mode non-blocking agar tidak menghambat loop utama
        self.sock.setblocking(False)
        print(f"[NET-BRIDGE] Pipa UDP menuju GCS aktif di {gcs_ip}:{udp_port}")

    def transmit_ship_status(self, raw_sensor_data, vision_data):
        """
        Mengemas umpan balik data sensor dan hasil deteksi objek menjadi JSON
        lalu menembakkannya ke Laptop darat secara real-time.
        """
        payload = {
            "timestamp": time.time(),
            "sensors": raw_sensor_data,  # Dictionary berisi data dari STM32
            "vision": vision_data        # Dictionary berisi hasil tracking YOLOv8
        }
        
        try:
            # Konversi data ke string JSON berformat bytes
            message = json.dumps(payload).encode('utf-8')
            self.sock.sendto(message, self.gcs_address)
        except Exception:
            # Abaikan error jika buffer internal sistem penuh sementara waktu
            pass

    def receive_commands(self):
        """
        Mendengarkan instruksi kendali taktis masuk dari Laptop darat.
        Mengembalikan None jika tidak ada paket baru di dalam buffer jaringan.
        """
        try:
            # Membaca data masuk dari buffer LAN (kapasitas 1024 bytes)
            data, addr = self.sock.recvfrom(1024)
            return json.loads(data.decode('utf-8'))
        except BlockingIOError:
            # Kondisi normal ketika belum ada data baru yang masuk ke soket
            return None
        except json.JSONDecodeError:
            print("[NET-BRIDGE] WARN: Paket perintah masuk rusak atau korup.")
            return None
        except Exception as e:
            print(f"[NET-BRIDGE] ERROR: Gagal membaca jaringan LAN: {e}")
            return None

    def close(self):
        """Menutup koneksi soket secara bersih saat sistem dimatikan"""
        self.sock.close()
        print("[NET-BRIDGE] Soket jaringan LAN resmi ditutup.")
