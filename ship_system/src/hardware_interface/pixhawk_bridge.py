# almasena-dev/ship_system/src/hardware_interface/pixhawk_bridge.py

from pymavlink import mavutil
import serial.tools.list_ports
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
        ports = serial.tools.list_ports.comports()
        for p in ports:
            if "1209:5741" in p.hwid or "Pixhawk" in p.description or "ArduPilot" in p.description:
                return p.device
        return fallback_port

    def connect(self):
        try:
            self.mav_conn = mavutil.mavlink_connection(self.port, baud=self.baudrate)
            self.mav_conn.wait_heartbeat()
            self.is_running = True

            self.set_mode('MANUAL')
            time.sleep(1)
            self.set_arm_state(arm=True)

            start_init = time.time()
            while time.time() - start_init < 2.0:
                self.send_movement_target()
                time.sleep(0.05)

            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            return True
        except Exception as e:
            print(f"[PIXHAWK] Error koneksi: {e}")
            self.is_running = False
            return False

    def set_mode(self, mode_name='MANUAL'):
        if self.is_running and self.mav_conn:
            try:
                mode_id = self.mav_conn.mode_mapping().get(mode_name)
                if mode_id is None: return

                target_sys = self.mav_conn.target_system or 1
                self.mav_conn.mav.set_mode_send(
                    target_sys,
                    mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                    mode_id
                )
            except Exception:
                pass

    def set_arm_state(self, arm=True):
        if self.is_running and self.mav_conn:
            try:
                target_sys = self.mav_conn.target_system or 1
                target_comp = self.mav_conn.target_component or 1
                arm_val = 1.0 if arm else 0.0

                self.mav_conn.mav.command_long_send(
                    target_sys, target_comp,
                    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                    0, arm_val, 21963, 0, 0, 0, 0, 0
                )
                self.is_armed = arm
            except Exception:
                pass

    def send_movement_target(self, pitch=1500, roll=1500, heave=1500, yaw=1500, surge=1500, sway=1500):
        if self.is_running and self.mav_conn:
            try:
                target_sys = self.mav_conn.target_system or 1
                target_comp = self.mav_conn.target_component or 1

                self.mav_conn.mav.rc_channels_override_send(
                    target_sys, target_comp,
                    int(pitch), # Ch 1: Pitch
                    int(roll),  # Ch 2: Roll
                    int(heave), # Ch 3: Heave / Naik-Turun (Standar ArduSub)
                    int(yaw),   # Ch 4: Yaw / Belok
                    int(surge), # Ch 5: Surge / Maju-Mundur (Standar ArduSub)
                    int(sway),  # Ch 6: Sway
                    0, 0
                )
            except Exception:
                pass

    def emergency_disarm_stop(self):
        if self.is_running and self.mav_conn:
            try:
                self.send_movement_target(1500, 1500, 1500, 1500, 1500, 1500)
                self.set_arm_state(arm=False)
            except Exception:
                pass

    def _read_loop(self):
        while self.is_running and self.mav_conn:
            try:
                msg = self.mav_conn.recv_match(blocking=True, timeout=0.1)
                if not msg: continue

                msg_type = msg.get_type()

                if msg_type == 'ATTITUDE':
                    self.latest_attitude_data["roll"] = math.degrees(msg.roll)
                    self.latest_attitude_data["pitch"] = math.degrees(msg.pitch)
                    yaw_deg = math.degrees(msg.yaw)
                    self.latest_attitude_data["heading"] = yaw_deg if yaw_deg >= 0 else (360 + yaw_deg)

                elif msg_type == 'VFR_HUD':
                    self.latest_attitude_data["depth_raw"] = abs(msg.alt)

                elif msg_type == 'HEARTBEAT':
                    is_armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    if is_armed != self.is_armed:
                        self.is_armed = is_armed

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
