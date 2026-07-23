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
    """Utility helper untuk membatasi rentang sinyal PWM agar aman untuk ESC"""
    return max(min_val, min(max_val, int(val)))

def main():
    print("[MAIN-SHIP] Memulai Orkestrasi Sistem ROV Almasena Candrassa...")

    config = load_config()
    net_cfg = config["network"]
    hw_cfg = config["hardware"]
    vis_cfg = config["vision"]

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

    if not stm32.connect():
        print("[MAIN-SHIP] WARN: Sistem berjalan tanpa kendali STM32.")

    if pixhawk.connect():
        # Sambungan sukses: PixhawkBridge secara otomatis akan mengirim 1500us (2 detik) untuk unlock ESC
        print("[MAIN-SHIP] Pixhawk 32 / Pixhawk 4 Terhubung & Inisialisasi ESC Selesai.")
    else:
        print("[MAIN-SHIP] WARN: Sistem berjalan tanpa kendali Pixhawk.")

    if vision.init_model():
        vision.start_cameras()
    else:
        print("[MAIN-SHIP] WARN: Engine AI YOLOv8 gagal berjalan.")

    loop_interval = 0.05  # Loop 20Hz
    print("[MAIN-SHIP] Seluruh modul sinkron. Memasuki Deterministic Cyclic Loop (~20Hz).")

    prev_autonomous = False
    auto_phase = "DESCENT"
    software_kill_active = False

    # Variable pelacak heartbeat paket UDP dari GCS (Failsafe)
    last_gcs_packet_time = time.time()
    gcs_timeout_threshold = 1.0  # 1 detik tanpa sinyal = Failsafe Disarm

    try:
        while True:
            loop_start = time.time()

            sensor_data = stm32.get_latest_sensors()
            attitude_data = pixhawk.get_latest_attitude()
            vision_data = vision.get_latest_vision()

            combined_telemetry = {**sensor_data, **attitude_data}
            gcs_commands = net.receive_commands()

            # --- 1. PARSING COMMAND & NETWORK FAILSAFE ---
            if gcs_commands:
                last_gcs_packet_time = time.time()  # Reset timer paket masuk
                kill_trigger = gcs_commands.get("kill_switch", False)

                if kill_trigger and not software_kill_active:
                    software_kill_active = True
                    print("[MAIN-SHIP] EMERGENCY: Software Kill Switch Dipicu!")
                else:
                    if software_kill_active and not kill_trigger:
                        print("[MAIN-SHIP] INFO: Kill Switch Dilepas. Re-Arming Pixhawk...")
                        pixhawk.set_arm_state(arm=True)
                    software_kill_active = kill_trigger
            else:
                # Failsafe: Koneksi UDP terputus > 1 detik
                if (time.time() - last_gcs_packet_time) > gcs_timeout_threshold:
                    if not software_kill_active:
                        print("[MAIN-SHIP] FAILSAFE: Koneksi UDP GCS Terputus! Memaksa Kill Switch...")
                        software_kill_active = True

            surge, yaw, heave, pitch = 0, 0, 0, 0
            ballast_cmd, gripper_cmd = 0, 0
            is_autonomous = False

            # --- 2. EVALUASI KONTROL & MODE OPERASIONAL ---
            if software_kill_active:
                surge, yaw, heave, pitch = 0, 0, 0, 0
                ballast_cmd = -99
                gripper_cmd = 0
                is_autonomous = False
                auto_phase = "MANUAL"

                # Paksa MAVLink DISARM dan kunci PWM ke 1500us (Diam)
                pixhawk.emergency_disarm_stop()

            else:
                # KONDISI NORMAL OPERASIONAL
                if gcs_commands:
                    is_autonomous = gcs_commands.get("autonomous_mode", False)
                    current_depth = sensor_data.get("depth_raw", 0.0)

                    if is_autonomous and not prev_autonomous:
                        auto_phase = "DESCENT"
                        print("[MAIN-SHIP] Mode Otonom Dipicu. Mulai Fase: DESCENT.")

                    prev_autonomous = is_autonomous

                    if not is_autonomous:
                        # Mode MANUAL / JOYSTICK
                        surge = gcs_commands.get("surge", 0)
                        yaw = gcs_commands.get("yaw", 0)
                        heave = gcs_commands.get("heave", 0)
                        pitch = gcs_commands.get("pitch", 0)

                        ballast_cmd = gcs_commands.get("ballast_cmd", 0)
                        gripper_cmd = gcs_commands.get("gripper_cmd", 0)
                    else:
                        # Mode OTONOM (AI Visual Tracking)
                        if vision_data.get("target_detected", False):
                            x_center, y_center, _, _ = vision_data["bbox"]
                            err_x = x_center - 320
                            err_y = y_center - 240

                            surge = 50   # Maju pelan
                            yaw = int(err_x * 0.8)
                            heave = int(err_y * -0.8)
                            ballast_cmd = 0
                        else:
                            if auto_phase == "DESCENT":
                                if current_depth >= 2.5:
                                    auto_phase = "ASCENT"
                                    surge, yaw = 0, 0
                                    heave = 50
                                    ballast_cmd = -1
                                else:
                                    surge, yaw = 0, 0
                                    heave = -50
                                    ballast_cmd = 1

                            elif auto_phase == "ASCENT":
                                if current_depth <= 0.2:
                                    auto_phase = "DESCENT"
                                    surge, yaw = 0, 0
                                    heave = -50
                                    ballast_cmd = 1
                                else:
                                    surge, yaw = 0, 0
                                    heave = 50
                                    ballast_cmd = -1

                # --- 3. KINEMATICS MIXER: KONVERSI INPUT KE PWM OVERRIDE (1100us - 1900us) ---
                # Normalisasi skala input (-100 s.d 100) menjadi faktor desimal (-1.0 s.d 1.0)
                norm_surge = surge / 100.0 if abs(surge) > 1.0 else surge
                norm_yaw = yaw / 100.0 if abs(yaw) > 1.0 else yaw

                # Kalkulasi offset sinyal PWM dari titik netral 1500us
                base_pwm = norm_surge * 300  # Maksimal offset ±300us (1200us s.d 1800us)
                turn_pwm = norm_yaw * 150    # Offset pembelokan

                # Differential Thrust untuk 4 Thruster Utama (MAIN OUT 1-4)
                ch1_pwm = clamp(1500 + base_pwm + turn_pwm)
                ch2_pwm = clamp(1500 + base_pwm - turn_pwm)
                ch3_pwm = clamp(1500 + base_pwm + turn_pwm)
                ch4_pwm = clamp(1500 + base_pwm - turn_pwm)

                # Kirim sinyal PWMOverride MAVLink langsung ke Pix32!
                pixhawk.send_thruster_pwm(ch1_pwm, ch2_pwm, ch3_pwm, ch4_pwm)

            # --- 4. INSTRUKSI PERIFERAL & TELEMETRI REFEED ---
            stm32.send_raw_control(ballast_speed=ballast_cmd, gripper_state=gripper_cmd)

            if "depth_raw" not in combined_telemetry:
                combined_telemetry["depth_raw"] = 0.0
            if "voltage_raw" not in combined_telemetry:
                combined_telemetry["voltage_raw"] = 0.0
            if "leak_status" not in combined_telemetry:
                combined_telemetry["leak_status"] = False

            combined_telemetry["software_kill_active"] = bool(software_kill_active)
            combined_telemetry["autonomous_active"] = bool(is_autonomous)
            combined_telemetry["auto_phase"] = str(auto_phase if is_autonomous else "MANUAL")

            net.transmit_ship_status(raw_sensor_data=combined_telemetry, vision_data=vision_data)

            # Jaga kestabilan deterministic loop 20Hz (50ms)
            elapsed_time = time.time() - loop_start
            time.sleep(max(0, loop_interval - elapsed_time))

    except KeyboardInterrupt:
        print("\n[MAIN-SHIP] Mematikan sistem via KeyboardInterrupt...")
    finally:
        print("[MAIN-SHIP] Membersihkan dan menutup seluruh subsistem...")
        vision.stop()
        pixhawk.close()
        stm32.close()
        net.close()
        print("[MAIN-SHIP] Seluruh subsistem lambung kapal resmi mati dengan aman.")

if __name__ == "__main__":
    main()
