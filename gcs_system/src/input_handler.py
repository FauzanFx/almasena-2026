# almasena-dev/gcs_system/src/input_handler.py

import pygame
import json
import os

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
                    "surge": {"axis": 1, "invert": True},
                    "yaw": {"axis": 0, "invert": False},
                    "pitch": {"axis": 3, "invert": True},
                    "ballast": {"axis": 2, "invert": False}
                },
                "buttons": {
                    "gripper_close": 3,
                    "gripper_open": 1,
                    "kill_switch": 8,
                    "autonomous": 9,
                    "hold_pitch": 2
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
                "autonomous_mode": False, "kill_switch": False, "hold_pitch": False
            }

        # 1. Analog Controls (-1000 s.d 1000)
        surge = self.read_axis("surge")
        yaw = self.read_axis("yaw")
        pitch = self.read_axis("pitch")
        
        # Ballast analog (-100 s.d 100 untuk STM32)
        ballast_cmd = int(self.read_axis("ballast") / 10)

        # 2. Gripper Command (-1, 0, 1)
        btn_cfg = self.config["buttons"]
        grip_close = self.joystick.get_button(btn_cfg["gripper_close"])
        grip_open = self.joystick.get_button(btn_cfg["gripper_open"])
        gripper_cmd = int(grip_open) - int(grip_close)

        # 3. Toggle Kill Switch (Select Button)
        curr_kill = self.joystick.get_button(btn_cfg["kill_switch"])
        if curr_kill and not self.prev_kill_btn:
            self.kill_toggle = not self.kill_toggle
        self.prev_kill_btn = curr_kill

        # 4. Toggle Autonomous (Start Button)
        curr_auto = self.joystick.get_button(btn_cfg["autonomous"])
        if curr_auto and not self.prev_auto_btn:
            self.autonomous_toggle = not self.autonomous_toggle
        self.prev_auto_btn = curr_auto

        # 5. Toggle Hold Pitch (X Button)
        curr_pitch = self.joystick.get_button(btn_cfg["hold_pitch"])
        if curr_pitch and not self.prev_pitch_btn:
            self.hold_pitch_toggle = not self.hold_pitch_toggle
        self.prev_pitch_btn = curr_pitch

        return {
            "surge": surge,
            "yaw": yaw,
            "heave": 0,  # Heave dikunci netral (0) karena dialihkan ke Ballast/STM32
            "pitch": pitch,
            "ballast_cmd": ballast_cmd,
            "gripper_cmd": gripper_cmd,
            "autonomous_mode": self.autonomous_toggle,
            "kill_switch": self.kill_toggle,
            "hold_pitch": self.hold_pitch_toggle
        }
