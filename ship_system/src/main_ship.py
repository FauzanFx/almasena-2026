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
from controls.pid_controller import MiniPID


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
        print("[MAIN-SHIP] Pixhawk 32 / Pixhawk 4 Terhubung & Inisialisasi ESC Selesai.")
    else:
        print("[MAIN-SHIP] WARN: Sistem berjalan tanpa kendali Pixhawk.")

    if vision.init_model():
        vision.start_cameras()
    else:
        print("[MAIN-SHIP] WARN: Engine AI YOLOv8 gagal berjalan.")

    # Init PID Controller
    # PID Depth membatasi output -100 s.d +100 (%) untuk mengendalikan kecepatan spuit STM32
    pid_depth = MiniPID(kp=100.0, ki=2.0, kd=5.0, output_limits=(-100, 100))
    pid_pitch = MiniPID(kp=3.0,   ki=0.1, kd=0.5, output_limits=(-100, 100))
    pid_yaw   = MiniPID(kp=2.0,   ki=0.0, kd=0.2, output_limits=(-100, 100))

    target_depth = 0.0
    target_heading = 0.0
    target_pitch = 0.0

    depth_hold_active = False
    heading_hold_active = False
    prev_hold_pitch_toggle = False

    loop_interval = 0.05  # Loop 20Hz (~50ms)
    print("[MAIN-SHIP] Seluruh modul sinkron. Memasuki Deterministic Cyclic Loop (~20Hz).")

    prev_autonomous = False
    auto_phase = "DESCENT"
    software_kill_active = False

    last_gcs_packet_time = time.time()
    gcs_timeout_threshold = 1.0  # Failsafe 1 Detik

    # Konstanta Limit Kecepatan Thruster (PWM Offset)
    SURGE_MAX_OFFSET = 400 * 0.5  # Max +-200 PWM
    PITCH_MAX_OFFSET = 300 * 0.5  # Max +-150 PWM
    YAW_MAX_OFFSET   = 300 * 0.5  # Max +-150 PWM

    try:
        while True:
            loop_start = time.time()

            sensor_data = stm32.get_latest_sensors()
            attitude_data = pixhawk.get_latest_attitude()
            vision_data = vision.get_latest_vision()

            current_depth = attitude_data.get("depth_raw", 0.0)
            current_pitch = attitude_data.get("pitch", 0.0)
            current_heading = attitude_data.get("heading", 0.0)

            combined_telemetry = {**sensor_data, **attitude_data}
            gcs_commands = net.receive_commands()

            # 1. Network Failsafe & Kill Switch Parsing
            if gcs_commands:
                last_gcs_packet_time = time.time()
                kill_trigger = gcs_commands.get("kill_switch", False)

                if kill_trigger and not software_kill_active:
                    software_kill_active = True
                    print("[MAIN-SHIP] EMERGENCY: Software Kill Switch Dipicu!")
                else:
                    if software_kill_active and not kill_trigger:
                        print("[MAIN-SHIP] INFO: Kill Switch Dilepas. Re-Arming Pixhawk...")
                        pixhawk.set_mode('MANUAL')
                        pixhawk.set_arm_state(arm=True)
                    software_kill_active = kill_trigger
            else:
                if (time.time() - last_gcs_packet_time) > gcs_timeout_threshold:
                    if not software_kill_active:
                        print("[MAIN-SHIP] FAILSAFE: Koneksi UDP GCS Terputus! Memaksa Kill Switch...")
                        software_kill_active = True

            surge, yaw, pitch_cmd = 0, 0, 0
            ballast_cmd, gripper_cmd = 0, 0
            is_autonomous = False
            hold_pitch_toggle = False

            # 2. Mode Operations Parsing
            if software_kill_active:
                surge, yaw, pitch_cmd = 0, 0, 0
                ballast_speed_stm32 = -99  # Kuras ballast saat darurat
                gripper_cmd = 0
                is_autonomous = False
                auto_phase = "MANUAL"

                depth_hold_active = False
                heading_hold_active = False
                pixhawk.emergency_disarm_stop()

            else:
                if gcs_commands:
                    is_autonomous = gcs_commands.get("autonomous_mode", False)
                    hold_pitch_toggle = gcs_commands.get("hold_pitch", False)

                    if is_autonomous and not prev_autonomous:
                        auto_phase = "DESCENT"
                        print("[MAIN-SHIP] Mode Otonom Dipicu. Mulai Fase: DESCENT.")

                    prev_autonomous = is_autonomous

                    if not is_autonomous:
                        surge = gcs_commands.get("surge", 0)
                        yaw = gcs_commands.get("yaw", 0)
                        pitch_cmd = gcs_commands.get("pitch", 0)

                        ballast_cmd = gcs_commands.get("ballast_cmd", 0)  # -100 s.d 100
                        gripper_cmd = gcs_commands.get("gripper_cmd", 0)
                    else:
                        if vision_data.get("target_detected", False):
                            x_center, y_center, _, _ = vision_data["bbox"]
                            err_x = x_center - 320
                            err_y = y_center - 240

                            surge = 500
                            yaw = int(err_x * 1.5)
                            ballast_cmd = int(err_y * -0.4)
                        else:
                            if auto_phase == "DESCENT":
                                if current_depth >= 2.5:
                                    auto_phase = "ASCENT"
                                    surge, yaw = 0, 0
                                    ballast_cmd = -80
                                else:
                                    surge, yaw = 0, 0
                                    ballast_cmd = 80

                            elif auto_phase == "ASCENT":
                                if current_depth <= 0.2:
                                    auto_phase = "DESCENT"
                                    surge, yaw = 0, 0
                                    ballast_cmd = 80
                                else:
                                    surge, yaw = 0, 0
                                    ballast_cmd = -80

                # 3. KONTROL KEDALAMAN / BALLAST (STM32 Offloading)
                if abs(ballast_cmd) > 0:
                    # Mode Manual: Forward kecepatan (-100 s.d 100) langsung ke STM32
                    ballast_speed_stm32 = ballast_cmd
                    target_depth = current_depth
                    depth_hold_active = False
                    pid_depth.reset()
                else:
                    # Mode Auto-Hold: PID menghitung kecepatan spuit otomatis untuk menahan kedalaman
                    depth_hold_active = True
                    ballast_speed_stm32 = int(max(-100, min(100, pid_depth.compute(target_depth, current_depth))))

                # 4. KONTROL PITCH (PIXHAWK) & PITCH HOLD
                raw_p = float(pitch_cmd)
                
                if hold_pitch_toggle:
                    # Pitch Hold Aktif (Edge Detection Lock)
                    if not prev_hold_pitch_toggle:
                        target_pitch = current_pitch
                        pid_pitch.reset()
                        print(f"[MAIN-SHIP] Pitch Hold AKTIF! Lock Target Pitch: {target_pitch:.2f}°")
                    
                    # Tahan sudut terkuci via PID Thruster Vertikal (Abaikan joystick)
                    pitch_axis = pid_pitch.compute(target_pitch, current_pitch)
                else:
                    # Pitch Hold Non-Aktif
                    if abs(raw_p) > 50:
                        # Control Manual via Gamepad
                        pitch_axis = (raw_p / 1000.0) * PITCH_MAX_OFFSET
                    else:
                        # Idle: Auto-Level Kembali ke 0 Derajat
                        pitch_axis = pid_pitch.compute(0.0, current_pitch)

                prev_hold_pitch_toggle = hold_pitch_toggle

                # 5. KONTROL YAW (PIXHAWK)
                raw_y = float(yaw)
                norm_yaw = raw_y / 1000.0
                if abs(raw_y) > 50:
                    heading_hold_active = False
                    yaw_axis = norm_yaw * YAW_MAX_OFFSET
                else:
                    if not heading_hold_active:
                        target_heading = current_heading
                        heading_hold_active = True
                        pid_yaw.reset()
                    yaw_axis = pid_yaw.compute(target_heading, current_heading)

                # 6. KONTROL SURGE (PIXHAWK)
                norm_surge = float(surge) / 1000.0
                surge_axis = norm_surge * SURGE_MAX_OFFSET

                # 7. Semburkan Target Sumbu ke Pixhawk (ArduSub simplerov Mixer)
                cmd_pitch = 1500  # Netral (Channel 1 tidak dipakai di simplerov)
                cmd_roll  = 1500  # Netral
                cmd_heave = clamp(1500 + pitch_axis)  # Channel 3 (Throttle) Mengendalikan Motor 1 & 2 untuk Pitch
                cmd_yaw   = clamp(1500 + yaw_axis)     # Channel 4 (Motor 3 & 4 Diferensial)
                cmd_surge = clamp(1500 + surge_axis)   # Channel 5 (Motor 3 & 4 Bersamaan)

                pixhawk.send_movement_target(
                    pitch=cmd_pitch,
                    roll=cmd_roll,
                    heave=cmd_heave,
                    yaw=cmd_yaw,
                    surge=cmd_surge
                )

            # 8. Kirim Perintah Kecepatan Spuit & Gripper ke STM32 via UART Serial
            stm32.send_raw_control(ballast_speed=ballast_speed_stm32, gripper_state=gripper_cmd)

            # 9. Feed Telemetri Kembali ke GCS
            if "voltage_raw" not in combined_telemetry:
                combined_telemetry["voltage_raw"] = 0.0
            if "leak_status" not in combined_telemetry:
                combined_telemetry["leak_status"] = False

            combined_telemetry["depth_raw"] = float(current_depth)
            combined_telemetry["software_kill_active"] = bool(software_kill_active)
            combined_telemetry["autonomous_active"] = bool(is_autonomous)
            combined_telemetry["auto_phase"] = str(auto_phase if is_autonomous else "MANUAL")
            combined_telemetry["depth_hold"] = bool(depth_hold_active)
            combined_telemetry["heading_hold"] = bool(heading_hold_active)
            combined_telemetry["pitch_hold"] = bool(hold_pitch_toggle)

            net.transmit_ship_status(raw_sensor_data=combined_telemetry, vision_data=vision_data)

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
