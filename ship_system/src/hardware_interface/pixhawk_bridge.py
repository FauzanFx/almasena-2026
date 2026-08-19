# almasena-dev/ship_system/src/hardware_interface/pixhawk_bridge.py

from pymavlink import mavutil
import serial.tools.list_ports # Modul sakti untuk auto-detect USB
import threading
import time
import math

class PixhawkBridge:
    def __init__(self, port="auto", baudrate=115200):
        self.baudrate = baudrate
        self.port = self._auto_detect_port(port)
        
        self.mav_conn = None
        self.is_running = False
        self.is_armed = False

        self.latest_attitude_data = {
            "heading": 0.0,
            "roll": 0.0,
            "pitch": 0.0,
            "depth_raw": 0.0
        }

    def _auto_detect_port(self, fallback_port):
        """Fungsi pelacak port USB otomatis berdasarkan Hardware ID Pixhawk"""
        print("[PIXHAWK-MAVLINK] Memindai port USB secara otomatis...")
        ports = serial.tools.list_ports.comports()
        
        for p in ports:
            # Cari VID:PID Pixhawk (1209:5741) atau kata kunci di deskripsinya
            if "1209:5741" in p.hwid or "Pixhawk" in p.description or "ArduPilot" in p.description:
                print(f"[PIXHAWK-MAVLINK] >> Ditemukan Pixhawk di: {p.device}")
                return p.device
                
        print(f"[PIXHAWK-MAVLINK] WARNING: Pixhawk tidak ditemukan otomatis! Menggunakan fallback: {fallback_port}")
        return fallback_port

    def connect(self):
        try:
            print(f"[PIXHAWK-MAVLINK] Mencoba menghubungkan ke {self.port}...")
            self.mav_conn = mavutil.mavlink_connection(self.port, baud=self.baudrate)

            print("[PIXHAWK-MAVLINK] Menunggu heartbeat dari Pixhawk...")
            self.mav_conn.wait_heartbeat()
            print("[PIXHAWK-MAVLINK] Heartbeat diterima! Holybro Pix32 Terhubung.")

            self.is_running = True

            print("[PIXHAWK-MAVLINK] Mengubah Mode Penerbangan ke MANUAL...")
            self.set_mode('MANUAL')
            time.sleep(1)

            print("[PIXHAWK-MAVLINK] Arming & Mengirim Sinyal Netral 1500us...")
            self.set_arm_state(arm=True)

            # Inisialisasi ESC dengan sinyal netral pada seluruh sumbu
            start_init = time.time()
            while time.time() - start_init < 2.0:
                self.send_movement_target()
                time.sleep(0.05)

            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            print("[PIXHAWK-MAVLINK] Inisialisasi & ESC Unlock Selesai. Siap Menerima Target Sumbu!")
            return True
        except Exception as e:
            print(f"[PIXHAWK-MAVLINK] ERROR: Gagal terhubung ke Pixhawk: {e}")
            self.is_running = False
            return False

    def set_mode(self, mode_name='MANUAL'):
        if self.is_running and self.mav_conn:
            try:
                mode_id = self.mav_conn.mode_mapping().get(mode_name)
                if mode_id is None:
                    print(f"[PIXHAWK-MAVLINK] ERROR: Mode {mode_name} tidak ditemukan.")
                    return

                target_sys = self.mav_conn.target_system if self.mav_conn.target_system else 1
                target_comp = self.mav_conn.target_component if self.mav_conn.target_component else 1

                self.mav_conn.mav.set_mode_send(
                    target_sys,
                    mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                    mode_id
                )
                print(f"[PIXHAWK-MAVLINK] Flight Mode diubah ke: {mode_name}")
            except Exception as e:
                print(f"[PIXHAWK-MAVLINK] ERROR: Gagal merubah mode: {e}")

    def set_arm_state(self, arm=True):
        if self.is_running and self.mav_conn:
            try:
                target_sys = self.mav_conn.target_system if self.mav_conn.target_system else 1
                target_comp = self.mav_conn.target_component if self.mav_conn.target_component else 1
                arm_val = 1.0 if arm else 0.0

                self.mav_conn.mav.command_long_send(
                    target_sys, target_comp,
                    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                    0, arm_val, 21963, 0, 0, 0, 0, 0
                )
                self.is_armed = arm
                status_str = "ARMED" if arm else "DISARMED"
                print(f"[PIXHAWK-MAVLINK] Status: >>> {status_str} <<<")
            except Exception as ex:
                print(f"[PIXHAWK-MAVLINK] ERROR: Gagal merubah status ARM/DISARM: {ex}")

    def send_movement_target(self, pitch=1500, roll=1500, heave=1500, yaw=1500, surge=1500, sway=1500):
        """Kirim perintah target sumbu (native RC channels) sesuai standar ArduSub mixer"""
        if self.is_running and self.mav_conn:
            try:
                target_sys = self.mav_conn.target_system if self.mav_conn.target_system else 1
                target_comp = self.mav_conn.target_component if self.mav_conn.target_component else 1

                self.mav_conn.mav.rc_channels_override_send(
                    target_sys, target_comp,
                    int(pitch),
                    int(roll),
                    int(heave),
                    int(yaw),
                    int(surge),
                    int(sway),
                    0, 0
                )
            except Exception as e:
                print(f"[PIXHAWK-MAVLINK] Gagal mengirim Movement Target: {e}")

    def emergency_disarm_stop(self):
        """Emergency Stop: Reset semua sumbu ke netral 1500us lalu DISARM"""
        if self.is_running and self.mav_conn:
            try:
                self.send_movement_target(1500, 1500, 1500, 1500, 1500, 1500)
                self.set_arm_state(arm=False)
            except Exception as e:
                print(f"[PIXHAWK-MAVLINK] Error pada Emergency Stop: {e}")

    def _read_loop(self):
        while self.is_running and self.mav_conn:
            try:
                msg = self.mav_conn.recv_match(blocking=True, timeout=0.1)
                if not msg:
                    continue

                msg_type = msg.get_type()

                if msg_type == 'ATTITUDE':
                    self.latest_attitude_data["roll"] = math.degrees(msg.roll)
                    self.latest_attitude_data["pitch"] = math.degrees(msg.pitch)
                    yaw_deg = math.degrees(msg.yaw)
                    self.latest_attitude_data["heading"] = yaw_deg if yaw_deg >= 0 else (360 + yaw_deg)

                elif msg_type == 'VFR_HUD':
                    self.latest_attitude_data["depth_raw"] = abs(msg.alt)

                elif msg_type == 'HEARTBEAT':
                    is_physically_armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    if is_physically_armed != self.is_armed:
                        self.is_armed = is_physically_armed

            except Exception:
                time.sleep(0.01)

    def get_latest_attitude(self):
        return self.latest_attitude_data

    def get_arm_status(self):
        return self.is_armed

    def close(self):
        self.emergency_disarm_stop()
        self.is_running = False
        if self.mav_conn:
            self.mav_conn.close()
        print("[PIXHAWK-MAVLINK] Jalur MAVLink resmi ditutup.")
