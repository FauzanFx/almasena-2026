import os
import sys
import time
import yaml
from pathlib import Path

# Setup Path Modul
current_file = Path(__file__).resolve()
ship_system_root = current_file.parents[2]
sys.path.append(os.path.join(ship_system_root, "src"))

from network.net_bridge import NetBridge
from hardware_interface.stm32_bridge import STM32Bridge

def load_config():
    config_path = os.path.join(ship_system_root, "config", "low_level_config.yaml")
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[TEST] CRITICAL ERROR: Gagal membaca file konfigurasi: {e}")
        sys.exit(1)

def main():
    print("[TEST] Memulai Test Ballast & Encoder via Joystick GCS...")

    config = load_config()
    net_cfg = config["network"]
    hw_cfg = config["hardware"]

    # Kita hanya butuh Network (ke GCS) dan STM32 (ke motor ballast)
    net = NetBridge(gcs_ip=net_cfg["gcs_ip"], udp_port=net_cfg["telemetry_port"])
    stm32 = STM32Bridge(port=hw_cfg["stm32_port"], baudrate=hw_cfg["serial_baudrate"])

    if stm32.connect():
        print(f"[STM32] Terhubung ke STM32 via {stm32.port}!")
        stm32.send_zeroing() # Reset encoder ke 0 saat mulai
    else:
        print(f"[STM32] ERROR: Gagal terhubung ke STM32!")
        sys.exit(1)

    loop_interval = 0.05
    last_debug_print = time.time()
    
    # Pengaman deteksi tombol zeroing
    prev_zero_cmd = False

    try:
        print("\n")
        while True:
            loop_start = time.time()

            # 1. BACA DATA DARI STM32 & GCS
            sensor_data = stm32.get_latest_sensors()
            gcs_commands = net.receive_commands() or {}

            # 2. EKSTRAK COMMAND JOYSTICK
            blst_cmd = gcs_commands.get('ballast_cmd', gcs_commands.get('ballast', 0))
            grp_cmd = gcs_commands.get('gripper_cmd', gcs_commands.get('grip', 0))
            z_cmd = gcs_commands.get('zero_encoder', False)

            # 3. LOGIKA ZEROING ENCODER (EDGE DETECTION)
            if z_cmd and not prev_zero_cmd:
                stm32.send_zeroing()
                print("\n[TEST] === ENCODER DI-RESET KE 0 VIA GCS! ===")
            prev_zero_cmd = z_cmd

            # 4. LOGIKA MOTOR BALLAST (OPEN-LOOP)
            # Normalisasi input joystick ke batas aman PWM (-100% sampai 100%)
            pwm_speed = int(blst_cmd) 
            pwm_speed = max(-100, min(100, pwm_speed))

            # Deadband kecil agar joystick tidak "ngedrift" saat dilepas
            if abs(pwm_speed) < 5:
                pwm_speed = 0

            # Kirim perintah kecepatan murni (tanpa PID)
            stm32.send_manual_speed(pwm_speed)
            
            # Kirim perintah gripper (pakai send_target_position karena argumen gripper menempel disitu)
            # Target position kita set 0 saja karena STM32 versi ini mengabaikan target posisinya.
            stm32.send_target_position(0, grp_cmd)

            # 5. CETAK DASHBOARD
            if loop_start - last_debug_print > 0.1:
                t_enc = sensor_data.get('encoder_ticks', 0)
                t_pwm = sensor_data.get('pwm_stm32', 0)
                t_grp = sensor_data.get('gripper_status', 0)
                
                # Format cetak 2 baris yang menimpa dirinya sendiri (seperti di main_ship)
                print(f"\r\033[K[NET-RX] Joystick Ballast: {blst_cmd:4} | Gripper: {grp_cmd:2} | Zero Btn: {z_cmd}")
                print(f"\r\033[K[STM32]  ENC: {t_enc} | PWM Motor: {pwm_speed}% | GRP State: {t_grp}\033[F", end="", flush=True)
                
                last_debug_print = loop_start

            # 6. KIRIM TELEMETRI KEMBALI KE GCS (Agar status di laptop GCS ter-update)
            # Kita lempar data sensor mentah ke GCS
            net.transmit_ship_status(raw_sensor_data=sensor_data, vision_data={})

            # Jaga loop rate
            elapsed_time = time.time() - loop_start
            time.sleep(max(0, loop_interval - elapsed_time))

    except KeyboardInterrupt:
        print("\n\n[TEST] Dihentikan oleh user. Mematikan sistem...")
    finally:
        # Failsafe: matikan motor saat keluar
        stm32.send_manual_speed(0)
        stm32.send_target_position(0, 0)
        time.sleep(0.1)
        stm32.close()
        net.close()
        print("[TEST] Selesai.")

if __name__ == "__main__":
    main()
