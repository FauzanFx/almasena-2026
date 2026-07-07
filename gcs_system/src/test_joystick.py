# almasena-dev/gcs_system/src/test_joystick.py
import pygame
import sys

pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("Gamepad tidak terdeteksi! Colok dulu stiknya.")
    sys.exit()

joy = pygame.joystick.Joystick(0)
joy.init()
print(f"Menguji Stik: {joy.get_name()}")
print("Gerakkan stik atau pencet tombol untuk melihat indeksnya. Tekan Ctrl+C untuk keluar.\n")

try:
    while True:
        pygame.event.pump()
        
        # 1. Cek semua Sumbu Analog (Axes)
        for i in range(joy.get_numaxes()):
            val = joy.get_axis(i)
            if abs(val) > 0.2: # Tampilkan jika digerakkan lebih dari deadzone
                print(f"[AXIS] Nomor Indeks: {i} -> Nilai: {val:.2f}")
                
        # 2. Cek semua Tombol (Buttons)
        for i in range(joy.get_numbuttons()):
            if joy.get_button(i):
                print(f"[BUTTON] Nomor Indeks: {i} -> DITEKAN")
                
        pygame.time.wait(100) # Delay biar terminal ga pusing membaca data
except KeyboardInterrupt:
    print("\nTes selesai.")
