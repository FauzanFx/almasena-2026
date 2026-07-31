import serial
import pygame
import time
import threading

SERIAL_PORT = '/dev/ttyACM0' 
BAUD_RATE = 115200

ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("Joystick tidak terdeteksi!")
    exit()

joystick = pygame.joystick.Joystick(0)
joystick.init()

# Variabel Global Limit
limit_min = -7500
limit_max = 11000
target_posisi = 11000

print(f"Terhubung ke: {joystick.get_name()}")
print("Panduan Terminal:")
print(" - Ketik P,Kp,Ki,Kd untuk tuning PID (Contoh: P,1.2,0.01,0.5)")
print(" - Ketik L,Min,Max untuk ubah limit Spuit (Contoh: L,0,12500)")
print(" - Ketik Z lalu Enter untuk RESET/Zeroing Encoder saat posisi spuit tertutup rapat")
print("-" * 50)

def read_terminal_input():
    global limit_min, limit_max, target_posisi
    while True:
        try:
            user_input = input().strip()
            if user_input.startswith("P"):
                ser.write((user_input + "\n").encode('utf-8'))
                print(f"\n>>> [PID UPDATE] {user_input}\n")
            
            elif user_input.startswith("L"):
                parts = user_input.split(",")
                if len(parts) == 3:
                    limit_min = int(parts[1])
                    limit_max = int(parts[2])
                    ser.write((user_input + "\n").encode('utf-8'))
                    print(f"\n>>> [LIMIT UPDATE] Min: {limit_min} | Max: {limit_max}\n")
            
            elif user_input == "Z" or user_input == "z":
                target_posisi = 0
                ser.write("Z\n".encode('utf-8'))
                print(f"\n>>> [ZEROING] Encoder di-Nol-kan! Anggap posisi ini sebagai 0.\n")
        except:
            pass

input_thread = threading.Thread(target=read_terminal_input, daemon=True)
input_thread.start()

print_counter = 0

try:
    while True:
        pygame.event.pump()

        axis_y = joystick.get_axis(1)
        if abs(axis_y) > 0.1: 
            target_posisi += int(-axis_y * 100)

            # Batasi target dengan variabel limit yang bisa diubah-ubah
            if target_posisi < limit_min: target_posisi = limit_min
            if target_posisi > limit_max: target_posisi = limit_max

        gripper_cmd = 0
        if joystick.get_button(0): gripper_cmd = -1
        elif joystick.get_button(1): gripper_cmd = 1

        command = f"C,{target_posisi},{gripper_cmd}\n"
        ser.write(command.encode('utf-8'))

        if ser.in_waiting > 0:
            feedback = ser.readline().decode('utf-8', errors='ignore').strip()
            print_counter += 1
            if print_counter >= 10:
                print(f"T: {target_posisi:<5} | {feedback}")
                print_counter = 0

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nKeluar...")
    ser.write(b"C,11000,0\n")
    ser.close()
    pygame.quit()
