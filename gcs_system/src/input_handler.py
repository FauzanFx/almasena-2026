import pygame
import json
import os
import time

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

        self.r3_press_start = 0.0
        self.r3_triggered = False

        self.l3_press_start = 0.0
        self.l3_triggered = False

        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gamepad_config.json")
        self.config = self.load_config()
        self.check_connection()

    def load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    cfg = json.load(f)
                    print(f"[INPUT-HANDLER] Konfigurasi dimuat dari: {self.config_path}")
                    return cfg
            except Exception as e:
                print(f"[INPUT-HANDLER] Gagal parsing {self.config_path}: {e}")

        print("[INPUT-HANDLER] Menggunakan konfigurasi fallback default!")
        return {
            "axes": {
                "surge": {"axis": 1, "invert": True},
                "yaw": {"axis": 0, "invert": False},
                "pitch": {"axis": 4, "invert": True},
                "ballast": {"axis": -1, "invert": False}
            },
            "buttons": {
                "gripper_close": 4,
                "gripper_open": 5,
                "ballast_in": 1,
                "ballast_out": 3,
                "kill_switch": 8,
                "autonomous": 9,
                "hold_pitch": 0,
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
        if not self.joystick:
            return 0

        cfg = self.config["axes"].get(name, {"axis": -1, "invert": False})
        axis_idx = cfg.get("axis", -1)

        if axis_idx < 0 or axis_idx >= self.joystick.get_numaxes():
            return 0

        val = self.joystick.get_axis(axis_idx)
        if abs(val) < 0.15:
            return 0

        scaled = int(val * 1000)
        return -scaled if cfg.get("invert", False) else scaled

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

        btn_cfg = self.config.get("buttons", {})
        num_btns = self.joystick.get_numbuttons()

        def get_btn(key, fallback_idx):
            idx = btn_cfg.get(key, fallback_idx)
            return self.joystick.get_button(idx) if 0 <= idx < num_btns else 0

        # --- LOGIKA GRIPPER (Button 4 & 5) ---
        grip_close = get_btn("gripper_close", 4)  # Button 4
        grip_open  = get_btn("gripper_open", 5)   # Button 5
        gripper_cmd = int(grip_open) - int(grip_close)

        # --- LOGIKA BALLAST DARI TOMBOL (Button 2 & 1) ---
        # Mengirim sinyal kecepatan ballast (misal ±100 pwm) saat tombol ditahan
        ballast_fill  = get_btn("ballast_in", 2)   # Button 2 (Mengisi / Maju)
        ballast_drain = get_btn("ballast_out", 1)  # Button 1 (Membuang / Mundur)
        ballast_cmd = 0
        if ballast_fill:
            ballast_cmd = 100
        elif ballast_drain:
            ballast_cmd = -100

        # --- TOGGLE BUTTONS ---
        curr_kill = get_btn("kill_switch", 8)
        if curr_kill and not self.prev_kill_btn:
            self.kill_toggle = not self.kill_toggle
            print(f"\n[INPUT] Failsafe Kill: {'AKTIF' if self.kill_toggle else 'NONAKTIF'}")
        self.prev_kill_btn = curr_kill

        curr_auto = get_btn("autonomous", 9)
        if curr_auto and not self.prev_auto_btn:
            self.autonomous_toggle = not self.autonomous_toggle
            print(f"\n[INPUT] Mode Otonom: {'AKTIF' if self.autonomous_toggle else 'MANUAL'}")
        self.prev_auto_btn = curr_auto

        curr_pitch = get_btn("hold_pitch", 3)
        if curr_pitch and not self.prev_pitch_btn:
            self.hold_pitch_toggle = not self.hold_pitch_toggle
            state_str = "AKTIF (HOLD)" if self.hold_pitch_toggle else "NONAKTIF (MANUAL)"
            print(f"\n[INPUT] Status Pitch Hold: >>> {state_str} <<<")
        self.prev_pitch_btn = curr_pitch

        now = time.time()

        # R3 (Zeroing)
        curr_r3 = get_btn("zero_encoder", 11)
        zero_trigger = False
        if curr_r3:
            if self.r3_press_start == 0.0:
                self.r3_press_start = now
            elif (now - self.r3_press_start > 1.5) and not self.r3_triggered:
                zero_trigger = True
                self.r3_triggered = True
                print("\n[INPUT] Sinyal Zeroing (R3) Terkirim!")
        else:
            self.r3_press_start = 0.0
            self.r3_triggered = False

        # L3 (Maxing)
        curr_l3 = get_btn("max_encoder", 10)
        max_trigger = False
        if curr_l3:
            if self.l3_press_start == 0.0:
                self.l3_press_start = now
            elif (now - self.l3_press_start > 1.5) and not self.l3_triggered:
                max_trigger = True
                self.l3_triggered = True
                print("\n[INPUT] Sinyal Max Limit (L3) Terkirim!")
        else:
            self.l3_press_start = 0.0
            self.l3_triggered = False

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
