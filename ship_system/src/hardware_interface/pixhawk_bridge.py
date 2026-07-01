# almasena-dev/ship_system/src/hardware_interface/pixhawk_bridge.py

from pymavlink import mavutil
import threading
import time
import math

class PixhawkBridge:
    def __init__(self, port="/dev/ttyACM1", baudrate=115200):
        # Biasanya jika STM32 di ttyACM0, Pixhawk akan terbaca di ttyACM1
        self.port = port
        self.baudrate = baudrate
        self.mav_conn = None
        self.is_running = False
        
        # Penampung data orientasi aktual (state interface) dari internal IMU Pixhawk
        self.latest_attitude_data = {
            "heading": 0.0,  # Derajat (0 - 360)
            "roll": 0.0,     # Derajat
            "pitch": 0.0     # Derajat
        }

    def connect(self):
        """Membuka jalur komunikasi serial MAVLink ke Pixhawk 4"""
        try:
            print(f"[PIXHAWK-MAVLINK] Mencoba menghubungkan ke {self.port}...")
            self.mav_conn = mavutil.mavlink_connection(self.port, baud=self.baudrate)
            
            # Menunggu detak jantung (heartbeat) pertama dari Pixhawk untuk memastikan koneksi aktif
            print("[PIXHAWK-MAVLINK] Menunggu heartbeat dari Pixhawk...")
            self.mav_conn.wait_heartbeat()
            print("[PIXHAWK-MAVLINK] Heartbeat diterima! Pixhawk 4 Terhubung.")
            
            self.is_running = True
            # Jalankan thread latar belakang untuk terus membaca data telemetri dari Pixhawk
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            return True
        except Exception as e:
            print(f"[PIXHAWK-MAVLINK] ERROR: Gagal terhubung ke Pixhawk: {e}")
            self.is_running = False
            return False

    def _read_loop(self):
        """Loop latar belakang untuk membaca pesan MAVLink masuk secara terus-menerus"""
        while self.is_running and self.mav_conn:
            try:
                # Membaca pesan apa saja yang masuk dari Pixhawk
                msg = self.mav_conn.recv_match(blocking=True, timeout=0.1)
                if not msg:
                    continue
                
                # Filter pesan spesifik ATTITUDE untuk mengambil data orientasi IMU
                if msg.get_type() == 'ATTITUDE':
                    # Pymavlink mengembalikan nilai dalam satuan radian, konversi langsung ke derajat
                    self.latest_attitude_data["roll"] = math.degrees(msg.roll)
                    self.latest_attitude_data["pitch"] = math.degrees(msg.pitch)
                    
                    # Kalkulasi heading dari radian yaw (range 0 sampai 360 derajat)
                    yaw_deg = math.degrees(msg.yaw)
                    self.latest_attitude_data["heading"] = yaw_deg if yaw_deg >= 0 else (360 + yaw_deg)
            except Exception:
                time.sleep(0.01)

    def send_manual_control(self, surge, yaw, heave, pitch=0):
        """
        Mengirimkan instruksi MANUAL_CONTROL (Remote virtual) ke Pixhawk 4.
        Parameter input bertipe integer dengan rentang standar MAVLink: -1000 hingga 1000.
        - surge: Maju (+) / Mundur (-)
        - yaw: Belok Kanan (+) / Belok Kiri (-)
        - heave: Naik (+) / Turun (-) -> Sesuai konfigurasi daya apung dinamis thruster vertikal
        """
        if self.is_running and self.mav_conn:
            try:
                # Target sistem ID 1 dan Komponen ID 1 (standar flight controller)
                target_system = self.mav_conn.target_system if self.mav_conn.target_system else 1
                
                # Kirim pesan MANUAL_CONTROL ke Pixhawk
                self.mav_conn.mav.manual_control_send(
                    target_system,
                    int(surge),  # x: pitch/surge control
                    int(yaw),    # y: roll/sway control (tidak dipakai di 4 thruster, di-set lewat yaw)
                    int(heave),  # z: thrust/heave control
                    int(yaw),    # r: yaw control
                    0            # buttons: bitmask untuk fungsi tambahan (0 = tidak ada)
                )
            except Exception as e:
                print(f"[PIXHAWK-MAVLINK] Gagal mengirim instruksi kendali: {e}")

    def get_latest_attitude(self):
        """Menyediakan data orientasi aktual untuk ditarik oleh Traffic Manager"""
        return self.latest_attitude_data

    def close(self):
        """Menutup koneksi MAVLink secara aman"""
        self.is_running = False
        if self.mav_conn:
            self.mav_conn.close()
        print("[PIXHAWK-MAVLINK] Jalur MAVLink resmi ditutup.")
