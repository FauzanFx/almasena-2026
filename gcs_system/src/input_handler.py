# almasena-dev/gcs_system/src/input_handler.py

import pygame
import json
import os
import time  # <-- Tambahkan untuk menghitung waktu double-click

class InputHandler:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()

        self.joystick = None
        self.autonomous_toggle = False
        self.kill_toggle = False
        self.hold_pitch_toggle = False

        self.prev_kill_btn = False
        self.prev_auto_btn = False
        self.prev_pitch_btn = False
        
        # Variabel untuk Double Click R3 dan L3
        self.prev_r3_btn = False
        self.r3_last_click_time = 0.0
        
        self.prev_l3_btn = False
        self.l3_last_click_time = 0.0
        
        self.double_click_threshold = 0.5 # Maksimal setengah detik antar klik

        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gamepad_config.json")
        self.config = self.load_config()
        self.check_connection()

    def load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                print(f"[GCS-INPUT] Memuat konfigurasi gamepad dari JSON.")
                return json.load(f)
        else:
            print("[GCS-INPUT] WARNING: gamepad_config.json tidak ditemukan! Menggunakan fallback default.")
            return {
                "axes": {
                    "surge": {"axis": 3, "invert": True},
                    "yaw": {"axis": 0, "invert": False},
                    "pitch": {"axis": 2, "invert": True},
                    "ballast": {"axis": 1, "invert": False}
                },
                "buttons": {
                    "gripper_close": 3,
                    "gripper_open": 1,
                    "kill_switch": 8,
                    "autonomous": 9,
                    "hold_pitch": 2,
                    "zero_encoder": 11, # R3
                    "max_encoder": 10   # L3
                }
            }

    def check_connection(self):
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            return True
        else:
            self.joystick = None
            return False

    def read_axis(self, name):
        cfg = self.config["axes"].get(name, {"axis": 0, "invert": False})
        val = self.joystick.get_axis(cfg["axis"])
        if abs(val) < 0.1:
            return 0
        scaled = int(val * 1000)
        return -scaled if cfg["invert"] else scaled

    def get_commands(self):
        pygame.event.pump()

        if not self.joystick and not self.check_connection():
            return {
                "surge": 0, "yaw": 0, "heave": 0, "pitch": 0,
                "ballast_cmd": 0, "gripper_cmd": 0,
                "autonomous_mode": False, "kill_switch": False, 
                "hold_pitch": False, "zero_encoder": False, "max_encoder": False
            }

        surge = self.read_axis("surge")
        yaw = self.read_axis("yaw")
        pitch = self.read_axis("pitch")
        ballast_cmd = int(self.read_axis("ballast") / 10)

        btn_cfg = self.config["buttons"]
        grip_close = self.joystick.get_button(btn_cfg.get("gripper_close", 3))
        grip_open = self.joystick.get_button(btn_cfg.get("gripper_open", 1))
        gripper_cmd = int(grip_open) - int(grip_close)

        curr_kill = self.joystick.get_button(btn_cfg.get("kill_switch", 8))
        if curr_kill and not self.prev_kill_btn:
            self.kill_toggle = not self.kill_toggle
        self.prev_kill_btn = curr_kill

        curr_auto = self.joystick.get_button(btn_cfg.get("autonomous", 9))
        if curr_auto and not self.prev_auto_btn:
            self.autonomous_toggle = not self.autonomous_toggle
        self.prev_auto_btn = curr_auto

        curr_pitch = self.joystick.get_button(btn_cfg.get("hold_pitch", 2))
        if curr_pitch and not self.prev_pitch_btn:
            self.hold_pitch_toggle = not self.hold_pitch_toggle
        self.prev_pitch_btn = curr_pitch

        # --- LOGIKA DOUBLE CLICK R3 (ZEROING) ---
        curr_r3 = self.joystick.get_button(btn_cfg.get("zero_encoder", 11))
        zero_trigger = False
        if curr_r3 and not self.prev_r3_btn:
            now = time.time()
            if now - self.r3_last_click_time < self.double_click_threshold:
                zero_trigger = True
                self.r3_last_click_time = 0.0 # Reset setelah berhasil
            else:
                self.r3_last_click_time = now
        self.prev_r3_btn = curr_r3

        # --- LOGIKA DOUBLE CLICK L3 (MAXING) ---
        curr_l3 = self.joystick.get_button(btn_cfg.get("max_encoder", 10))
        max_trigger = False
        if curr_l3 and not self.prev_l3_btn:
            now = time.time()
            if now - self.l3_last_click_time < self.double_click_threshold:
                max_trigger = True
                self.l3_last_click_time = 0.0 # Reset setelah berhasil
            else:
                self.l3_last_click_time = now
        self.prev_l3_btn = curr_l3

        return {
            "surge": surge,
            "yaw": yaw,
            "heave": 0, 
            "pitch": pitch,
            "ballast_cmd": ballast_cmd,
            "gripper_cmd": gripper_cmd,
            "autonomous_mode": self.autonomous_toggle,
            "kill_switch": self.kill_toggle,
            "hold_pitch": self.hold_pitch_toggle,
            "zero_encoder": zero_trigger,
            "max_encoder": max_trigger
        }
