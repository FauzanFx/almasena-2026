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
        self.write_lock = threading.Lock()

        self.latest_sensor_data = {
            "encoder_ticks": 0,
            "ballast_speed": 0,
            "gripper_status": 0
        }

    def connect(self):
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.1
            )
            self.is_running = True
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            print(f"[STM32-SERIAL] Sukses terhubung ke port {self.port} @ {self.baudrate} bps.")
            return True
        except Exception as e:
            print(f"[STM32-SERIAL] ERROR: Gagal membuka koneksi serial fisik: {e}")
            self.is_running = False
            return False

    def _read_loop(self):
        while self.is_running and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    raw_line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                    if raw_line:
                        self._parse_raw_string(raw_line)
            except Exception:
                time.sleep(0.01)

    def _parse_raw_string(self, raw_string):
        """
        Memecah format dari STM32: "ENC:1234 | SPD:50 | GRP:1"
        """
        try:
            parts = raw_string.split('|')
            data_dict = {}
            for part in parts:
                if ':' in part:
                    key, value = part.split(':')
                    data_dict[key.strip()] = value.strip()

            self.latest_sensor_data["encoder_ticks"] = int(data_dict.get("ENC", 0))
            self.latest_sensor_data["ballast_speed"] = int(data_dict.get("SPD", 0))
            self.latest_sensor_data["gripper_status"] = int(data_dict.get("GRP", 0))
        except Exception:
            pass

    def send_raw_control(self, ballast_speed, gripper_state=0):
        if self.is_running and self.serial_conn and self.serial_conn.is_open:
            cmd_string = f"{int(ballast_speed)},{int(gripper_state)}\n"
            with self.write_lock:
                try:
                    self.serial_conn.write(cmd_string.encode('utf-8'))
                except Exception as e:
                    print(f"[STM32-SERIAL] Gagal mengirim perintah: {e}")

    def get_latest_sensors(self):
        return self.latest_sensor_data

    def close(self):
        self.is_running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        print("[STM32-SERIAL] Pipa komunikasi fisik ditutup.")
