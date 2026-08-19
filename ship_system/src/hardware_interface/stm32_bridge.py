import serial
import serial.tools.list_ports
import threading
import time
import json
import os

class STM32Bridge:
    def __init__(self, port="/dev/serial0", baudrate=115200):
        self.baudrate = baudrate
        self.port = self._auto_detect_port(port)
        self.serial_conn = None
        self.is_running = False
        self.write_lock = threading.Lock()
        self.pid_config_file = "pid_config.json"

        self.latest_sensor_data = {
            "encoder_ticks": 0,
            "target_stm32": 0,
            "pwm_stm32": 0,
            "ballast_speed": 0,
            "gripper_status": 0
        }

    def _auto_detect_port(self, fallback_port):
        # --- PERBAIKAN: Bersihkan trailing slash agar Linux tidak menganggapnya folder ---
        if isinstance(fallback_port, str):
            fallback_port = fallback_port.rstrip('/')

        if os.path.exists("/dev/serial0"):
            return "/dev/serial0"
        elif fallback_port and os.path.exists(fallback_port):
            return fallback_port
        return fallback_port

    def connect(self):
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=0.1)
            self.is_running = True
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()

            time.sleep(1.5)
            self.load_and_inject_pid()
            return True
        except Exception as e:
            print(f"[STM32] Gagal koneksi: {e}")
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
        try:
            parts = raw_string.split('|')
            data = {}
            for p in parts:
                if ':' in p:
                    k, v = p.split(':', 1)
                    data[k.strip()] = v.strip()

            self.latest_sensor_data.update({
                "target_stm32": int(data.get("TGT", self.latest_sensor_data["target_stm32"])),
                "pwm_stm32": int(data.get("PWM", self.latest_sensor_data["pwm_stm32"])),
                "encoder_ticks": int(data.get("ENC", self.latest_sensor_data["encoder_ticks"])),
                "ballast_speed": int(data.get("SPD", self.latest_sensor_data["pwm_stm32"])),
                "gripper_status": int(data.get("GRP", self.latest_sensor_data["gripper_status"]))
            })
        except Exception:
            pass

    def send_target_position(self, target_pos, gripper_state=0):
        if self.is_running and self.serial_conn and self.serial_conn.is_open:
            cmd = f"C,{int(target_pos)},{int(gripper_state)}\n"
            with self.write_lock:
                try: self.serial_conn.write(cmd.encode('utf-8'))
                except Exception: pass

    def send_pid_tuning(self, kp: float, ki: float, kd: float):
        if self.is_running and self.serial_conn and self.serial_conn.is_open:
            cmd = f"P,{float(kp):.3f},{float(ki):.3f},{float(kd):.3f}\n"
            with self.write_lock:
                try: self.serial_conn.write(cmd.encode('utf-8'))
                except Exception: pass

    def send_zeroing(self):
        if self.is_running and self.serial_conn and self.serial_conn.is_open:
            with self.write_lock:
                try: self.serial_conn.write(b"Z\n")
                except Exception: pass

    def save_pid_config(self, kp: float, ki: float, kd: float):
        self.send_pid_tuning(kp, ki, kd)
        try:
            with open(self.pid_config_file, 'w') as f:
                json.dump({"Kp": kp, "Ki": ki, "Kd": kd}, f, indent=4)
        except Exception as e:
            print(f"[STM32] Gagal save PID: {e}")

    def load_and_inject_pid(self):
        if os.path.exists(self.pid_config_file):
            try:
                with open(self.pid_config_file, 'r') as f:
                    data = json.load(f)
                    self.send_pid_tuning(
                        float(data.get("Kp", 1.0)),
                        float(data.get("Ki", 0.0)),
                        float(data.get("Kd", 0.0))
                    )
            except Exception as e:
                print(f"[STM32] Gagal load PID: {e}")

    def get_latest_sensors(self):
        return self.latest_sensor_data

    def close(self):
        self.is_running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
