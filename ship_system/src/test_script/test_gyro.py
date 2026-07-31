import time
import math
import sys
from pymavlink import mavutil

# Berdasarkan log terminal lu sebelumnya, Pixhawk terdeteksi di /dev/ttyACM0
PIXHAWK_PORT = '/dev/ttyACM0'
BAUDRATE = 115200

print(f"Connecting to Pixhawk via MAVLink on {PIXHAWK_PORT}...")
# Membuka jalur komunikasi serial MAVLink
master = mavutil.mavlink_connection(PIXHAWK_PORT, baud=BAUDRATE)

print("Waiting for heartbeat...")
# Menunggu sinyal detak jantung (heartbeat) pertama dari Pixhawk
master.wait_heartbeat()
print("Heartbeat received! Pixhawk 4 is connected and broadcasting.")
print("Mulai membaca data gyro. Gerakkan Pixhawk lu untuk melihat perubahan sudut!\n")

try:
    while True:
        # Menangkap paket data spesifik berlabel 'ATTITUDE'
        msg = master.recv_match(type='ATTITUDE', blocking=True, timeout=1.0)
        
        if msg:
            # Data asli MAVLink dikirim dalam satuan Radian. 
            # Kita konversi ke Derajat (Degree) agar manusiawi saat dibaca di lab.
            roll_deg = math.degrees(msg.roll)
            pitch_deg = math.degrees(msg.pitch)
            yaw_deg = math.degrees(msg.yaw)
            
            # Cetak log secara interaktif di baris yang sama
            log_msg = f"\r[RAW-MAVLINK] Roll: {roll_deg:6.2f}° | Pitch: {pitch_deg:6.2f}° | Yaw: {yaw_deg:6.2f}°"
            sys.stdout.write(log_msg)
            sys.stdout.flush()
            
        time.sleep(0.05) # Loop terkunci di frekuensi ~20Hz

except KeyboardInterrupt:
    print("\n\nTesting MAVLink dihentikan dengan aman.")
