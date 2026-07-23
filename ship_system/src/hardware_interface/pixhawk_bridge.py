# almasena-dev/ship_system/src/hardware_interface/pixhawk_bridge.py

from pymavlink import mavutil
import threading
import time
import math

class PixhawkBridge:
    def __init__(self, port="/dev/ttyACM0", baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.mav_conn = None
        self.is_running = False
        self.is_armed = False

        self.latest_attitude_data = {
            "heading": 0.0,
            "roll": 0.0,
            "pitch": 0.0
        }

    def connect(self):
        try:
            print(f"[PIXHAWK-MAVLINK] Mencoba menghubungkan ke {self.port}...")
            self.mav_conn = mavutil.mavlink_connection(self.port, baud=self.baudrate)

            print("[PIXHAWK-MAVLINK] Menunggu heartbeat dari Pixhawk...")
            self.mav_conn.wait_heartbeat()
            print("[PIXHAWK-MAVLINK] Heartbeat diterima! Holybro Pix32 Terhubung.")

            self.is_running = True
            
            # --- MANDATORY ESC UNLOCK SEQUENCE (1500us Neutral Signal) ---
            print("[PIXHAWK-MAVLINK] Mengirim Sinyal Netral 1500us untuk Unlock ESC...")
            self.set_arm_state(arm=True)
            self.send_thruster_pwm(1500, 1500, 1500, 1500)
            time.sleep(2)  # Tahan 2 detik agar ESC berbunyi netral
            
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            return True
        except Exception as e:
            print(f"[PIXHAWK-MAVLINK] ERROR: Gagal terhubung ke Pixhawk: {e}")
            self.is_running = False
            return False

    def set_arm_state(self, arm=True):
        if self.is_running and self.mav_conn:
            try:
                target_sys = self.mav_conn.target_system if self.mav_conn.target_system else 1
                target_comp = self.mav_conn.target_component if self.mav_conn.target_component else 1
                arm_val = 1.0 if arm else 0.0

                # Kirim MAV_CMD_COMPONENT_ARM_DISARM dengan Magic Code ArduPilot (21963)
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

    def send_thruster_pwm(self, ch1_pwm, ch2_pwm, ch3_pwm, ch4_pwm):
        """MENGIRIM OVERRIDE PWM DIREK (1100us - 1900us) KE MAIN OUT 1-4"""
        if self.is_running and self.mav_conn:
            try:
                target_sys = self.mav_conn.target_system if self.mav_conn.target_system else 1
                target_comp = self.mav_conn.target_component if self.mav_conn.target_component else 1

                self.mav_conn.mav.rc_channels_override_send(
                    target_sys, target_comp,
                    int(ch1_pwm), int(ch2_pwm), int(ch3_pwm), int(ch4_pwm),
                    0, 0, 0, 0
                )
            except Exception as e:
                print(f"[PIXHAWK-MAVLINK] Gagal mengirim PWM Override: {e}")

    def emergency_disarm_stop(self):
        """Emergency Stop: DISARM + Kirim PWM Netral 1500us"""
        if self.is_running and self.mav_conn:
            try:
                self.send_thruster_pwm(1500, 1500, 1500, 1500)
                self.set_arm_state(arm=False)
            except Exception as e:
                print(f"[PIXHAWK-MAVLINK] Error pada Emergency Stop: {e}")

    def _read_loop(self):
        while self.is_running and self.mav_conn:
            try:
                msg = self.mav_conn.recv_match(blocking=True, timeout=0.1)
                if not msg:
                    continue

                if msg.get_type() == 'ATTITUDE':
                    self.latest_attitude_data["roll"] = math.degrees(msg.roll)
                    self.latest_attitude_data["pitch"] = math.degrees(msg.pitch)
                    yaw_deg = math.degrees(msg.yaw)
                    self.latest_attitude_data["heading"] = yaw_deg if yaw_deg >= 0 else (360 + yaw_deg)

                elif msg.get_type() == 'HEARTBEAT':
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
