# almasena-dev/gcs_system/src/input_handler.py

import pygame

class InputHandler:
    def __init__(self):
        # Inisialisasi modul joystick milik pygame
        pygame.init()
        pygame.joystick.init()
        
        self.joystick = None
        self.autonomous_toggle = False
        self.prev_button_state = False
        
        # State internal untuk mengunci posisi gripper (0: Terbuka/Idle, 1: Menjepit/Mengunci)
        self.gripper_state = 0 

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
        """
        Mengubah nilai mentah analog pygame (-1.0 s/d 1.0) 
        menjadi rentang standar MAVLink Pixhawk (-1000 s/d 1000)
        """
        # Deadzone dinamis agar stik tidak terlalu sensitif (mencegah drifting)
        if abs(val) < 0.1:
            return 0
            
        scaled = int(val * 1000)
        return -scaled if invert else scaled

    def get_commands(self):
        """
        Membaca event internal pygame dan menyusun seluruh input 
        menjadi dictionary paket komando untuk dikirim ke ROV.
        """
        pygame.event.pump()
        
        # Proteksi jika stik mendadak putus di tengah latihan
        if not self.joystick:
            if not self.check_connection():
                return {
                    "surge": 0, "yaw": 0, "heave": 0, "pitch": 0,
                    "ballast_speed": 0, "fin_angle": 90, "gripper_state": self.gripper_state,
                    "autonomous_mode": False
                }

        # 1. Pemetaan Sumbu Analog Navigasi (MAVLink Standard)
        surge = self.scale_axis(self.joystick.get_axis(1), invert=True) 
        yaw = self.scale_axis(self.joystick.get_axis(0))
        heave = self.scale_axis(self.joystick.get_axis(2), invert=True) 
        pitch = 0 

        # 2. Pemetaan Tombol Periferal Ballast Tank & Sirip Kemudi
        ballast_speed = 0
        if self.joystick.get_button(5):     # Tombol R1
            ballast_speed = 150
        elif self.joystick.get_button(4):   # Tombol L1
            ballast_speed = -150

        fin_angle = 90
        if self.joystick.get_numhats() > 0:
            hat = self.joystick.get_hat(0)
            if hat[0] == 1:    
                fin_angle = 135
            elif hat[0] == -1: 
                fin_angle = 45

        # 3. KENDALI GRIPPER (LOGIKA DUAL-BUTTON STATE LOCK)
        # Jika Button 0 (Tombol A) ditekan -> Gripper mengunci/menjepit target QR Code
        if self.joystick.get_button(0):
            if self.gripper_state != 1:
                self.gripper_state = 1
                print("[GCS-INPUT] Perintah Periferal: MENCENGKRAM GRIPPER (State: 1)")
                
        # Jika Button 1 (Tombol B) ditekan -> Gripper melepas/membuka
        elif self.joystick.get_button(1):
            if self.gripper_state != 0:
                self.gripper_state = 0
                print("[GCS-INPUT] Perintah Periferal: MELEPAS GRIPPER (State: 0)")

        # 4. Logika Toggle Tombol Otonom (Tombol START / Button 9)
        current_button_state = self.joystick.get_button(9)
        if current_button_state and not self.prev_button_state:
            self.autonomous_toggle = not self.autonomous_toggle
            print(f"[GCS-INPUT] Switch Otonom Berubah Menjadi: {self.autonomous_toggle}")
            
        self.prev_button_state = current_button_state

        # Kembalikan paket data lengkap terintegrasi
        return {
            "surge": surge,
            "yaw": yaw,
            "heave": heave,
            "pitch": pitch,
            "ballast_speed": ballast_speed,
            "fin_angle": fin_angle,
            "gripper_state": self.gripper_state, # Variabel gripper dikirim di sini
            "autonomous_mode": self.autonomous_toggle
        }
