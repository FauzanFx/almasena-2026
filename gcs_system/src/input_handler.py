# almasena-dev/gcs_system/src/input_handler.py

import pygame

class InputHandler:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()

        self.joystick = None
        self.autonomous_toggle = False
        self.kill_toggle = False
        self.prev_button_state = False
        self.prev_kill_button_state = False  # Menyimpan state tombol kill sebelumnya
        self.check_connection()

    def check_connection(self):
        joystick_count = pygame.joystick.get_count()
        if joystick_count > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            print(f"[GCS-INPUT] Terhubung ke Gamepad: {self.joystick.get_name()}")
            return True
        else:
            self.joystick = None
            return False

    def scale_axis(self, val, invert=False):
        if abs(val) < 0.1:
            return 0
        scaled = int(val * 1000)
        return -scaled if invert else scaled

    def get_commands(self):
        pygame.event.pump()

        BTN_UP    = 4
        BTN_DOWN  = 6
        BTN_LEFT  = 5
        BTN_RIGHT = 7
        BTN_BACK  = 8   # Tombol BACK/SELECT
        BTN_START = 9

        if not self.joystick:
            if not self.check_connection():
                return {
                    "surge": 0, "yaw": 0, "heave": 0, "pitch": 0,
                    "ballast_cmd": 0, "gripper_cmd": 0,
                    "autonomous_mode": False, "kill_switch": False
                }

        surge = self.scale_axis(self.joystick.get_axis(1), invert=True)
        yaw = self.scale_axis(self.joystick.get_axis(0))
        heave = self.scale_axis(self.joystick.get_axis(2), invert=True)
        pitch = 0

        state_up    = self.joystick.get_button(BTN_UP)
        state_down  = self.joystick.get_button(BTN_DOWN)
        state_left  = self.joystick.get_button(BTN_LEFT)
        state_right = self.joystick.get_button(BTN_RIGHT)

        # 3. Logika Toggle Tombol Darurat Kill Switch (Edge Detection)
        current_kill_state = self.joystick.get_button(BTN_BACK)
        if current_kill_state and not self.prev_kill_button_state:
            self.kill_toggle = not self.kill_toggle
            print(f"[GCS-INPUT] Switch Kill: {self.kill_toggle}")
        
        # PERBAIKAN: Selalu kunci state tombol saat ini untuk evaluasi loop berikutnya
        self.prev_kill_button_state = current_kill_state

        ballast_cmd = int(state_down) - int(state_up)
        gripper_cmd = int(state_right) - int(state_left)

        
        current_button_state = self.joystick.get_button(BTN_START)
        if current_button_state and not self.prev_button_state:
            self.autonomous_toggle = not self.autonomous_toggle
            print(f"[GCS-INPUT] Switch Otonom: {self.autonomous_toggle}")

        self.prev_button_state = current_button_state

        return {
            "surge": surge,
            "yaw": yaw,
            "heave": heave,
            "pitch": pitch,
            "ballast_cmd": ballast_cmd,
            "gripper_cmd": gripper_cmd,
            "autonomous_mode": self.autonomous_toggle,
            "kill_switch": self.kill_toggle
        }
