# almasena-dev/ship_system/src/main_ship.py

import os
import sys
import time
import yaml
from pathlib import Path

# Setup Path Modul
current_file = Path(__file__).resolve()
ship_system_root = current_file.parents[1]
sys.path.append(os.path.join(ship_system_root, "src"))

from network.net_bridge import NetBridge
from hardware_interface.stm32_bridge import STM32Bridge
from hardware_interface.pixhawk_bridge import PixhawkBridge
from vision.vision_processor import VisionProcessor


def load_config():
    config_path = os.path.join(ship_system_root, "config", "low_level_config.yaml")
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[MAIN-SHIP] CRITICAL ERROR: Gagal membaca file konfigurasi: {e}")
        sys.exit(1)

def clamp(val, min_val=1100, max_val=1900):
    return max(min_val, min(max_val, int(val)))


def main():
    print("[MAIN-SHIP] Memulai Test Isolasi Direct Control...")

    config = load_config()
    net_cfg = config["network"]
    hw_cfg = config["hardware"]
    vis_cfg = config["vision"]

    net = NetBridge(gcs_ip=net_cfg["gcs_ip"], udp_port=net_cfg["telemetry_port"])
    stm32 = STM32Bridge(port=hw_cfg["stm32_port"], baudrate=hw_cfg["serial_baudrate"])
    pixhawk = PixhawkBridge(port=hw_cfg["pixhawk_port"], baudrate=hw_cfg["serial_baudrate"])

    stm32.connect()
    
    if pixhawk.connect():
        pixhawk.set_mode('MANUAL')
        pixhawk.set_arm_state(arm=True)
    else:
        print("[MAIN-SHIP] ERROR: Pixhawk gagal terhubung!")
        sys.exit(1)

    loop_interval = 0.05  # 20Hz

    try:
        while True:
            loop_start = time.time()
            gcs_commands = net.receive_commands()

            surge_val = 0
            yaw_val = 0
            heave_val = 0

            if gcs_commands:
                # 1. BACA NILAI MENTAH DARI GCS
                surge_val = gcs_commands.get("surge", 0)
                yaw_val   = gcs_commands.get("yaw", 0)
                heave_val = gcs_commands.get("heave", 0)

                # PRINT PRINT LIVE UNTUK VERIFIKASI SUMBU SENSOR
                print(f"[UDP-RECEIVED] SURGE: {surge_val:5d} | YAW: {yaw_val:5d} | HEAVE: {heave_val:5d}")

            # 2. CONVERT KE OFFSET PWM (Skala -1000 s.d 1000 -> ±300us)
            s_pwm = int((float(surge_val) / 1000.0) * 300)
            y_pwm = int((float(yaw_val) / 1000.0) * 150)
            h_pwm = int((float(heave_val) / 1000.0) * 300)

            # 3. DIRECT MAPPING TANPA PID ATAU LOGIKA LAIN
            ch1_pwm = clamp(1500 + s_pwm + y_pwm)  # Main Out 1: Horizontal Kanan (Surge + Yaw)
            ch2_pwm = clamp(1500 + s_pwm - y_pwm)  # Main Out 2: Horizontal Kiri  (Surge - Yaw)
            ch3_pwm = clamp(1500 + h_pwm)          # Main Out 3: Vertikal Kanan   (Heave)
            ch4_pwm = clamp(1500 + h_pwm)          # Main Out 4: Vertikal Kiri    (Heave)

            pixhawk.send_thruster_pwm(ch1_pwm, ch2_pwm, ch3_pwm, ch4_pwm)

            elapsed_time = time.time() - loop_start
            time.sleep(max(0, loop_interval - elapsed_time))

    except KeyboardInterrupt:
        print("\n[MAIN-SHIP] Mematikan sistem...")
    finally:
        pixhawk.close()
        stm32.close()
        net.close()

if __name__ == "__main__":
    main()
