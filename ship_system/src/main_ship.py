# almasena-dev/ship_system/src/main_ship.py

import os
import sys
import time
import yaml
from pathlib import Path

# Registrasi path root untuk kebutuhan modul internal src
current_file = Path(__file__).resolve()
ship_system_root = current_file.parents[1]
sys.path.append(os.path.join(ship_system_root, "src"))

from network.net_bridge import NetBridge
from hardware_interface.stm32_bridge import STM32Bridge
from hardware_interface.pixhawk_bridge import PixhawkBridge
from vision.vision_processor import VisionProcessor

def load_config():
    """Memuat parameter network, hardware, dan vision dari file YAML"""
    config_path = os.path.join(ship_system_root, "config", "low_level_config.yaml")
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[MAIN-SHIP] CRITICAL ERROR: Gagal membaca file konfigurasi: {e}")
        sys.exit(1)

def main():
    print("[MAIN-SHIP] Memulai Orkestrasi Sistem ROV Almasena Candrassa...")

    config = load_config()
    net_cfg = config["network"]
    hw_cfg = config["hardware"]
    vis_cfg = config["vision"]

    # Inisialisasi objek driver subsistem komunikasi dan hardware
    net = NetBridge(gcs_ip=net_cfg["gcs_ip"], udp_port=net_cfg["telemetry_port"])
    stm32 = STM32Bridge(port=hw_cfg["stm32_port"], baudrate=hw_cfg["serial_baudrate"])
    pixhawk = PixhawkBridge(port=hw_cfg["pixhawk_port"], baudrate=hw_cfg["serial_baudrate"])
    vision = VisionProcessor(
        model_path=vis_cfg["model_path"],
        gcs_ip=net_cfg["gcs_ip"],
        port_front=net_cfg["video_port_front"],
        port_bottom=net_cfg["video_port_bottom"],
        cam_front_idx=vis_cfg["cam_front"],
        cam_bottom_idx=vis_cfg["cam_bottom"]
    )

    # Membuka koneksi fisik ke perangkat keras dan model YOLOv8
    if not stm32.connect():
        print("[MAIN-SHIP] WARN: Sistem berjalan tanpa kendali STM32.")

    if not pixhawk.connect():
        print("[MAIN-SHIP] WARN: Sistem berjalan tanpa kendali Pixhawk 4.")

    if vision.init_model():
        vision.start_cameras()
    else:
        print("[MAIN-SHIP] WARN: Engine AI YOLOv8 gagal berjalan.")

    # Sinkronisasi frekuensi eksekusi loop utama di 20Hz (50ms)
    loop_interval = 0.05
    print("[MAIN-SHIP] Seluruh modul sinkron. Memasuki Deterministic Cyclic Loop (~20Hz).")

    prev_autonomous = False
    auto_phase = "DESCENT"

    try:
        while True:
            loop_start = time.time()

            # Membaca Data Sensor Aktual
            sensor_data = stm32.get_latest_sensors()
            attitude_data = pixhawk.get_latest_attitude()
            vision_data = vision.get_latest_vision()

            combined_telemetry = {**sensor_data, **attitude_data}
            gcs_commands = net.receive_commands()

            # Logika Pemilihan Mode Kontrol
            surge, yaw, heave, pitch = 0, 0, 0, 0
            ballast_cmd, fin_angle, gripper_cmd = 0, 90, 0
            is_autonomous = False

            if gcs_commands:
                is_autonomous = gcs_commands.get("autonomous_mode", False)
                current_depth = sensor_data.get("depth_raw", 0.0)

                # Batas aman operasional kedalaman kolam (meter)
                MAX_SAFE_DEPTH = 2.5
                MIN_SAFE_DEPTH = 0.2

                # Reset fase otonom ke awal (DESCENT) saat tombol baru dipicu
                if is_autonomous and not prev_autonomous:
                    auto_phase = "DESCENT"
                    print("[MAIN-SHIP] Mode Otonom Dipicu. Mulai Fase: DESCENT.")

                prev_autonomous = is_autonomous

                if not is_autonomous:
                    # Jalur 1: Parsing Data Input Manual dari Pilot di GCS
                    surge = gcs_commands.get("surge", 0)
                    yaw = gcs_commands.get("yaw", 0)
                    heave = gcs_commands.get("heave", 0)
                    pitch = gcs_commands.get("pitch", 0)
                    
                    ballast_cmd = gcs_commands.get("ballast_cmd", 0)
                    fin_angle = gcs_commands.get("fin_angle", 90)
                    gripper_cmd = gcs_commands.get("gripper_cmd", 0)
                else:
                    # Jalur 2: Logika Kendali Otomatis berbasis Visi Komputer
                    if vision_data["target_detected"]:
                        # Target Terkunci: Hitung deviasi koordinat X/Y untuk visual servoing menuju objek
                        x_center, y_center, _, _ = vision_data["bbox"]
                        err_x = x_center - 320
                        err_y = y_center - 240

                        surge = 100
                        yaw = int(err_x * 0.8)
                        heave = int(err_y * -0.8)
                        ballast_cmd = 0 
                    else:
                        # Target Hilang: Eksekusi pola Yo-Yo (Naik-Turun) mencari objek
                        if auto_phase == "DESCENT":
                            if current_depth >= MAX_SAFE_DEPTH:
                                auto_phase = "ASCENT"
                                print(f"[MAIN-SHIP] Dasar ({current_depth}m) tercapai. Switch ke Fase: ASCENT.")
                                surge, yaw = 0, 0
                                heave = 300
                                ballast_cmd = -1  # Menguras air ballast tank
                            else:
                                surge, yaw = 0, 0
                                heave = -300
                                ballast_cmd = 1   # Mengisi air ballast tank

                        elif auto_phase == "ASCENT":
                            if current_depth <= MIN_SAFE_DEPTH:
                                auto_phase = "DESCENT"
                                print(f"[MAIN-SHIP] Permukaan ({current_depth}m) tercapai. Switch ke Fase: DESCENT.")
                                surge, yaw = 0, 0
                                heave = -300
                                ballast_cmd = 1
                            else:
                                surge, yaw = 0, 0
                                heave = 300
                                ballast_cmd = -1

            # Kirim data navigasi utama ke Pixhawk
            pixhawk.send_manual_control(surge=surge, yaw=yaw, heave=heave, pitch=pitch)
            
            # Kirim instruksi periferal tambahan ke STM32
            stm32.send_raw_control(ballast_speed=ballast_cmd, fin_angle=fin_angle, gripper_state=gripper_cmd)

            # Kembalikan status log telemetri dan data visi ke GCS laptop
            combined_telemetry["autonomous_active"] = is_autonomous
            combined_telemetry["auto_phase"] = auto_phase if is_autonomous else "MANUAL"
            net.transmit_ship_status(raw_sensor_data=combined_telemetry, vision_data=vision_data)

            # Kalkulasi kompensasi waktu tidur agar frekuensi loop presisi di 20Hz
            elapsed_time = time.time() - loop_start
            time.sleep(max(0, loop_interval - elapsed_time))

    except KeyboardInterrupt:
        print("\n[MAIN-SHIP] Mematikan sistem via KeyboardInterrupt...")
    finally:
        vision.stop()
        pixhawk.close()
        stm32.close()
        net.close()
        print("[MAIN-SHIP] Seluruh subsistem lambung kapal resmi mati dengan aman.")

if __name__ == "__main__":
    main()
