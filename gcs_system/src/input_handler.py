# almasena-dev/gcs_system/src/input_handler.py

import pygame

class InputHandler:
    def __init__(self):
        # Inisialisasi modul joystick pygame
        pygame.init()
        pygame.joystick.init()

        self.joystick = None
        self.autonomous_toggle = False
        self.prev_button_state = False

        # Cek ketersediaan gamepad saat aplikasi dibuka
        self.check_connection()

    def check_connection(self):
        """Memeriksa apakah ada gamepad yang terhubung ke laptop"""
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
        """Membaca event internal dan menyusun seluruh input"""
        pygame.event.pump()

	# Indeks Button Mapping
        BTN_UP    = 4   # Tombol Mengeluarkan isi Balast Tank
        BTN_DOWN  = 6   # Tombol Mengisi Balast Tank
        BTN_LEFT  = 5   # Tombol Menjepit Gripper
        BTN_RIGHT = 7   # Tombol Melepas Jepitan Gripper
        BTN_START = 9   # Tombol Start untuk Toggle Otonom

        # Proteksi jika stik terputus
        if not self.joystick:
            if not self.check_connection():
                return {
                    "surge": 0, "yaw": 0, "heave": 0, "pitch": 0,
                    "ballast_cmd": 0, "fin_angle": 90, "gripper_cmd": 0,
                    "autonomous_mode": False
                }

        # 1. Pemetaan MAVLink Standard
        surge = self.scale_axis(self.joystick.get_axis(1), invert=True)
        yaw = self.scale_axis(self.joystick.get_axis(0))
        heave = self.scale_axis(self.joystick.get_axis(2), invert=True)
        pitch = 0

        # 2. Ambil Boolean dari Tombol Periferal (True/False)
        state_up    = self.joystick.get_button(BTN_UP)
        state_down  = self.joystick.get_button(BTN_DOWN)
        state_left  = self.joystick.get_button(BTN_LEFT)
        state_right = self.joystick.get_button(BTN_RIGHT)

        # 3. EKSEKUSI LOGIKA MUTUAL CANCELLATION (Hold-to-Run)
        ballast_cmd = int(state_down) - int(state_up)
        gripper_cmd = int(state_right) - int(state_left)

        # 4. Pemetaan Sirip Kemudi
        fin_angle = 90
        if self.joystick.get_numhats() > 0:
            hat = self.joystick.get_hat(0)
            if hat[0] == 1:
                fin_angle = 135
            elif hat[0] == -1:
                fin_angle = 45

        # 5. Logika Toggle Tombol Otonom
        current_button_state = self.joystick.get_button(BTN_START)
        if current_button_state and not self.prev_button_state:
            self.autonomous_toggle = not self.autonomous_toggle
            print(f"[GCS-INPUT] Switch Otonom: {self.autonomous_toggle}")

        self.prev_button_state = current_button_state

        # Mengembalikan Kumpulan Nilai Command
        return {
            "surge": surge,
            "yaw": yaw,
            "heave": heave,
            "pitch": pitch,
            "ballast_cmd": ballast_cmd,
            "fin_angle": fin_angle,
            "gripper_cmd": gripper_cmd,
            "autonomous_mode": self.autonomous_toggle
        }
