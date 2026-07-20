# almasena-dev/ship_system/src/network/net_bridge.py

import socket
import json
import time
import sys

class NetBridge:
    def __init__(self, gcs_ip="192.168.1.15", udp_port=5006, listen_port=5005):
        self.gcs_address = (gcs_ip, udp_port)

        # Inisialisasi soket UDP lokal untuk media komunikasi Ethernet
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # ---------------------------------------------------------------
        # PERBAIKAN UTAMA: WAJIB BIND PORT AGAR RASPI BISA MENDENGAR GCS
        # ---------------------------------------------------------------
        # Mengikat soket ke port 5005 agar bisa menangkap data masuk dari GCS
        self.sock.bind(('0.0.0.0', listen_port))

        # Mengatur soket ke mode non-blocking agar tidak menghambat loop utama
        self.sock.setblocking(False)
        print(f"[NET-BRIDGE] Pipa UDP aktif. Kirim ke GCS={gcs_ip}:{udp_port} | Mendengar di port={listen_port}")

    def transmit_ship_status(self, raw_sensor_data, vision_data):
        """
        Mengemas umpan balik data sensor dan hasil deteksi objek menjadi JSON
        lalu menembakkannya ke Laptop darat secara real-time.
        """
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
        """
        Mendengarkan instruksi kendali taktis masuk dari Laptop darat.
        Mengembalikan None jika tidak ada paket baru di dalam buffer jaringan.
        """
        try:
            # Membaca data masuk dari buffer LAN (kapasitas 1024 bytes)
            data, addr = self.sock.recvfrom(1024)
            commands = json.loads(data.decode('utf-8'))

            # ---------------------------------------------------------------
            # LOG LIVE RECEPTOR (Cetak pergerakan stik lokal Raspi)
            # ---------------------------------------------------------------
            if commands and isinstance(commands, dict):
                log_msg = (
                    f"\r[NET-RX LIVE] "
                    f"Surge: {commands.get('surge', 0):4d} | "
                    f"Yaw: {commands.get('yaw', 0):4d} | "
                    f"Heave: {commands.get('heave', 0):4d} | "
                    f"Ballast: {commands.get('ballast_cmd', 0):2d} | "
                    f"Fin: {commands.get('fin_angle', 90):3d}° | "
                    f"Grip: {commands.get('gripper_cmd', 0):2d} | "
                    f"Auto-Cmd: {str(commands.get('autonomous_mode', False)):5s}"
                )
                sys.stdout.write(log_msg)
                sys.stdout.flush()

            return commands
            
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
