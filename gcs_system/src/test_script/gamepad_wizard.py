# almasena-dev/gcs_system/src/gamepad_wizard.py

import pygame
import json
import os
import time

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gamepad_config.json")

def wait_for_neutral(joystick):
    """Memastikan semua analog dan tombol dilepas (posisi netral) sebelum input baru."""
    while True:
        pygame.event.pump()
        axis_busy = any(abs(joystick.get_axis(i)) > 0.3 for i in range(joystick.get_numaxes()))
        btn_busy = any(joystick.get_button(i) for i in range(joystick.get_numbuttons()))
        if not axis_busy and not btn_busy:
            break
        time.sleep(0.05)

def wait_for_axis(joystick, prompt_text, used_axes):
    print(f"\n[WIZARD] {prompt_text}")
    input("--> Tekan ENTER di terminal jika sudah siap, lalu gerakkan analog...")
    wait_for_neutral(joystick)

    while True:
        pygame.event.pump()
        for i in range(joystick.get_numaxes()):
            val = joystick.get_axis(i)
            if abs(val) > 0.7:
                if i in used_axes:
                    print(f"    [WARNING] Axis {i} SUDAH DIGUNAKAN! Gunakan analog yang berbeda.")
                    time.sleep(1.0)
                    wait_for_neutral(joystick)
                    break
                
                print(f"    [OK] Terdeteksi Axis {i} (nilai: {val:.2f})")
                used_axes.add(i)
                time.sleep(0.5)
                invert = True if val < 0 else False
                return {"axis": i, "invert": invert}
        time.sleep(0.05)

def wait_for_button(joystick, prompt_text, used_buttons):
    print(f"\n[WIZARD] {prompt_text}")
    input("--> Tekan ENTER di terminal jika sudah siap, lalu tekan tombol gamepad...")
    wait_for_neutral(joystick)

    while True:
        pygame.event.pump()
        for i in range(joystick.get_numbuttons()):
            if joystick.get_button(i):
                if i in used_buttons:
                    print(f"    [WARNING] Tombol ID {i} SUDAH DIGUNAKAN! Pilih tombol lain.")
                    time.sleep(1.0)
                    wait_for_neutral(joystick)
                    break

                print(f"    [OK] Terdeteksi Tombol ID {i}")
                used_buttons.add(i)
                time.sleep(0.5)
                return i
        time.sleep(0.05)

def main():
    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print("[ERROR] Gamepad tidak terdeteksi! Sambungkan gamepad terlebih dahulu.")
        return

    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    print(f"==================================================")
    print(f"   GAMEPAD MAPPING WIZARD - ROV ALMASENA")
    print(f"   Gamepad: {joystick.get_name()}")
    print(f"==================================================")

    config = {"axes": {}, "buttons": {}}
    used_axes = set()
    used_buttons = set()

    # 1. Mapping Analog / Axes
    config["axes"]["surge"]   = wait_for_axis(joystick, "1. SURGE  : Dorong Analog Kiri ke ATAS (Maju)", used_axes)
    config["axes"]["yaw"]     = wait_for_axis(joystick, "2. YAW    : Dorong Analog Kiri ke KANAN", used_axes)
    config["axes"]["pitch"]   = wait_for_axis(joystick, "3. PITCH  : Dorong Analog Kanan ke ATAS (Nose Up)", used_axes)
    config["axes"]["ballast"] = wait_for_axis(joystick, "4. BALLAST: Dorong Analog Kanan ke KANAN (Isi Air)", used_axes)

    # 2. Mapping Buttons
    config["buttons"]["gripper_close"] = wait_for_button(joystick, "5a. GRIPPER CLOSE: Tekan Tombol Y (Genggam)", used_buttons)
    config["buttons"]["gripper_open"]  = wait_for_button(joystick, "5b. GRIPPER OPEN : Tekan Tombol B (Lepas)", used_buttons)
    config["buttons"]["kill_switch"]   = wait_for_button(joystick, "6.  KILL SWITCH  : Tekan Tombol SELECT/BACK", used_buttons)
    config["buttons"]["autonomous"]    = wait_for_button(joystick, "7.  AUTONOMOUS   : Tekan Tombol START", used_buttons)
    config["buttons"]["hold_pitch"]    = wait_for_button(joystick, "8.  HOLD PITCH    : Tekan Tombol X", used_buttons)

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

    print(f"\n[SUCCESS] Konfigurasi berhasil disimpan tanpa duplikasi ke:\n{CONFIG_FILE}")

if __name__ == "__main__":
    main()
