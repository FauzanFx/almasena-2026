# almasena-dev/ship_system/src/main_ship.py

import os
import sys
import time
import yaml
from pathlib import Path

# Daftarkan folder src ke dalam sys.path agar Python mengenali modul internal kita
current_file = Path(__file__).resolve()
ship_system_root = current_file.parents[1]  # Naik ke folder 'ship_system'
sys.path.append(os.path.join(ship_system_root, "src"))

from network.net_bridge import NetBridge
from hardware_interface.stm32_bridge import STM32Bridge
from hardware_interface.pixhawk_bridge import PixhawkBridge
from vision.vision_processor import VisionProcessor

def load_config():
    """Memuat file konfigurasi YAML secara dinamis dengan Path Absolut"""
    config_path = os.path.join(ship_system_root, "config", "low_level_config.yaml")
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[MAIN-SHIP] CRITICAL ERROR: Gagal membaca file konfigurasi: {e}")
        sys.exit(1)

def main():
    print("[MAIN-SHIP] Memulai Orkestrasi Sistem ROV Almasena Candrassa...")
    
    # 1. Load Parameter dari Config
    config = load_config()
    net_cfg = config["network"]
    hw_cfg = config["hardware"]
    vis_cfg = config["vision"]

    # 2. Inisialisasi Seluruh Subsistem (Resource Management)
    net = NetBridge(gcs_ip=net_cfg["gcs_ip"], udp_port=net_cfg["telemetry_port"])
    
    stm32 = STM32Bridge(port=hw_cfg["stm32_port"], baudrate=hw_cfg["serial_baudrate"])
    
    pixhawk = PixhawkBridge(port=hw_cfg["pixhawk_port"], baudrate=hw_cfg["serial_baudrate"])
    
    vision = VisionProcessor(
        model_path=vis_cfg["model_path"],
        gcs_ip=net_cfg["gcs_ip"],
        port_front=net_cfg["video_port_front"],
        port_bottom=net_cfg["video_port_bottom"]
    )

    # 3. Mengaktifkan Jalur Koneksi Perangkat Keras
    if not stm32.connect():
        print("[MAIN-SHIP] WARN: Sistem berjalan tanpa kendali STM32.")
        
    if not pixhawk.connect():
        print("[MAIN-SHIP] WARN: Sistem berjalan tanpa kendali Pixhawk 4.")
        
    if vision.init_model():
        vision.start_cameras()
    else:
        print("[MAIN-SHIP] WARN: Engine AI YOLOv8 gagal berjalan.")

    # Frekuensi loop dikunci di ~20Hz (1 detak per 0.05 detik / 50 milidetik)
    loop_interval = 0.05 
    print("[MAIN-SHIP] Seluruh modul sinkron. Memasuki Deterministic Cyclic Loop (~20Hz).")

    # Manajer Status State Machine Otonom
    prev_autonomous = False
    auto_phase = "DESCENT"  # Pilihan fase: "DESCENT" atau "ASCENT"

    try:
        while True:
            loop_start = time.time()

            # ==========================================
            # STAGE 1: READ (Membaca Data Sensor Aktual)
            # ==========================================
            sensor_data = stm32.get_latest_sensors()
            attitude_data = pixhawk.get_latest_attitude()
            vision_data = vision.get_latest_vision()
            
            combined_telemetry = {**sensor_data, **attitude_data}
            gcs_commands = net.receive_commands()

            # ==========================================
            # STAGE 2: UPDATE (Logika Pemilihan Mode Kontrol)
            # ==========================================
            surge, yaw, heave, pitch = 0, 0, 0, 0
            ballast_speed, fin_angle, gripper_state = 0, 90, 0

            if gcs_commands:
                is_autonomous = gcs_commands.get("autonomous_mode", False)
                current_depth = sensor_data.get("depth_raw", 0.0)
                
                # Konfigurasi batas deteksi kedalaman kolam
                MAX_SAFE_DEPTH = 2.5  # Batas maksimum lantai kolam (dalam meter)
                MIN_SAFE_DEPTH = 0.2  # Batas minimum permukaan air (dalam meter)

                # Deteksi transisi tombol (Rising Edge) saat otonom baru saja dinyalakan
                if is_autonomous and not prev_autonomous:
                    auto_phase = "DESCENT"
                    print("[MAIN-SHIP] Mode Otonom Dipicu. Mulai Mencari Target ke Bawah (Fase: DESCENT).")
                
                prev_autonomous = is_autonomous

                # Evaluasi Jalur Kendali Akhir
                if not is_autonomous:
                    # ---- MODE KENDALI MANUAL PILOT ----
                    surge = gcs_commands.get("surge", 0)
                    yaw = gcs_commands.get("yaw", 0)
                    heave = gcs_commands.get("heave", 0)
                    pitch = gcs_commands.get("pitch", 0)
                    
                    ballast_speed = gcs_commands.get("ballast_speed", 0)
                    fin_angle = gcs_commands.get("fin_angle", 90)
                    gripper_state = gcs_commands.get("gripper_state", 0)
                else:
                    # ---- MODE KENDALI OTONOM AKTIF (AI SWITCH ON) ----
                    if vision_data["target_detected"]:
                        # ---------------------------------------------------
                        # KONDISI A: TARGET QR CODE BERHASIL DIKUNCI!
                        # ---------------------------------------------------
                        # Kunci target langsung memotong alur perjalanan yo-yo
                        x_center, y_center, w, h = vision_data["bbox"]
                        err_x = x_center - 320
                        err_y = y_center - 240
                        
                        # Jalankan Visual Servoing presisi menuju target
                        surge = 100               
                        yaw = int(err_x * 0.8)    
                        heave = int(err_y * -0.8) 
                        ballast_speed = 0         # Stabilisasi penuh dialihkan ke thruster vertikal
                        
                    else:
                        # ---------------------------------------------------
                        # KONDISI B: TARGET BELUM KETEMU (Pola Yo-Yo Loop)
                        # ---------------------------------------------------
                        if auto_phase == "DESCENT":
                            if current_depth >= MAX_SAFE_DEPTH:
                                # Jika mentok dasar tapi zonk, balik arah naik ke atas
                                auto_phase = "ASCENT"
                                print(f"[MAIN-SHIP] Dasar kolam ({current_depth}m) tercapai tanpa target.")
                                print("[MAIN-SHIP] Memutar arah pergerakan otonom ke Fase: ASCENT.")
                                
                                surge, yaw = 0, 0
                                heave = 300           # Pendorong vertikal menekan ke atas
                                ballast_speed = -150  # Kuras tangki ballast untuk menambah buoyancy
                            else:
                                # Terus meluncur turun mencari target
                                surge, yaw = 0, 0
                                heave = -300          
                                ballast_speed = 150   # Sedot air ballast tank
                                
                        elif auto_phase == "ASCENT":
                            if current_depth <= MIN_SAFE_DEPTH:
                                # DI SINI KUNCINYA: Jika sampai permukaan air target belum ketemu,
                                # jangan matikan sistem, tapi cemplungkan kembali robot ke bawah!
                                auto_phase = "DESCENT"
                                print(f"[MAIN-SHIP] Kembali ke permukaan ({current_depth}m) tanpa hasil.")
                                print("[MAIN-SHIP] Memulai putaran penyelaman ulang ke Fase: DESCENT!")
                                
                                surge, yaw = 0, 0
                                heave = -300          
                                ballast_speed = 150
                            else:
                                # Terus bergerak naik menuju permukaan
                                surge, yaw = 0, 0
                                heave = 300           
                                ballast_speed = -150  # Lanjutkan proses pengosongan tangki ballast

            # ==========================================
            # STAGE 3: WRITE (Eksekusi ke Hardware Fisik)
            # ==========================================
            pixhawk.send_manual_control(surge=surge, yaw=yaw, heave=heave, pitch=pitch)
            stm32.send_raw_control(ballast_speed=ballast_speed, fin_angle=fin_angle, gripper_state=gripper_state)

            # Update status telemetri untuk dikirim ke Ground Control Station
            combined_telemetry["autonomous_active"] = is_autonomous
            combined_telemetry["auto_phase"] = auto_phase if is_autonomous else "MANUAL"

            net.transmit_ship_status(raw_sensor_data=combined_telemetry, vision_data=vision_data)

            elapsed_time = time.time() - loop_start
            time.sleep(max(0, loop_interval - elapsed_time))

    except KeyboardInterrupt:
        print("\n[MAIN-SHIP] Menerima instruksi interupsi keyboard. Mematikan sistem...")
    finally:
        vision.stop()
        pixhawk.close()
        stm32.close()
        net.close()
        print("[MAIN-SHIP] Seluruh subsistem lambung kapal resmi mati dengan aman.")

if __name__ == "__main__":
    main()
