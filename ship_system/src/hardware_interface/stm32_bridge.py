# almasena-dev/ship_system/src/hardware_interface/stm32_bridge.py

import serial
import threading
import time

class STM32Bridge:
    def __init__(self, port="/dev/ttyACM0", baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.is_running = False
        
        # Thread safety lock untuk mencegah tabrakan data saat mengirim instruksi
        self.write_lock = threading.Lock()
        
        # Penampung data sensor aktual hasil parsing dari STM32
        self.latest_sensor_data = {
            "leak_status": 0,    # 0 = Aman, 1 = Kebocoran terdeteksi
            "depth_raw": 0.0,    # Nilai kedalaman mentah dalam meter
            "voltage_raw": 0.0   # Tegangan baterai utama dalam Volt
        }

    def connect(self):
        """Membuka jalur fisik serial dan mengaktifkan thread pembaca latar belakang"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.1
            )
            self.is_running = True
            
            # Alokasikan thread latar belakang khusus untuk membaca buffer serial
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            print(f"[STM32-SERIAL] Sukses terhubung ke port {self.port} @ {self.baudrate} bps.")
            return True
        except Exception as e:
            print(f"[STM32-SERIAL] ERROR: Gagal membuka koneksi serial fisik: {e}")
            self.is_running = False
            return False

    def _read_loop(self):
        """Loop pasif latar belakang yang terus-menerus menguras buffer data masuk"""
        while self.is_running and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    # Membaca baris data dari STM32 hingga karakter newline '\n'
                    raw_line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                    if raw_line:
                        self._parse_raw_string(raw_line)
            except Exception:
                time.sleep(0.01)

    def _parse_raw_string(self, raw_string):
        """
        Memecah string telemetri mentah dari STM32 Nucleo.
        Ekspektasi format dari firmware STM32: "LEAK:0,DEPTH:1.45,VOLT:14.2"
        """
        try:
            parts = raw_string.split(',')
            data_dict = {}
            for part in parts:
                key, value = part.split(':')
                data_dict[key.strip()] = float(value.strip())
            
            # Perbarui kontainer memori internal dengan konversi tipe data yang tepat
            self.latest_sensor_data["leak_status"] = int(data_dict.get("LEAK", 0))
            self.latest_sensor_data["depth_raw"] = data_dict.get("DEPTH", 0.0)
            self.latest_sensor_data["voltage_raw"] = data_dict.get("VOLT", 0.0)
        except Exception:
            # Mengabaikan paket data jika terjadi kehilangan byte di kabel data
            pass

    def send_raw_control(self, ballast_speed, gripper_state):
        """
        Mengirimkan instruksi kendali mentah langsung ke unit aktuator STM32.
        Format paket keluar ke STM32: "CMD,ballast_speed, gripper_state\n"
        """
        if self.is_running and self.serial_conn and self.serial_conn.is_open:
            # Membangun string perintah seminimal mungkin untuk efisiensi parser C/C++ di STM32
            cmd_string = f"CMD,{ballast_speed},{gripper_state}\n"
            
            with self.write_lock:
                try:
                    self.serial_conn.write(cmd_string.encode('utf-8'))
                except Exception as e:
                    print(f"[STM32-SERIAL] Gagal melemparkan perintah ke hardware: {e}")

    def get_latest_sensors(self):
        """Menyediakan data sensor aktual untuk ditarik oleh Traffic Manager"""
        return self.latest_sensor_data

    def close(self):
        """Mematikan thread dan menutup port hardware secara bersih"""
        self.is_running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        print("[STM32-SERIAL] Pipa komunikasi fisik ditutup secara aman.")
