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

from network.net_bridge_remote import NetBridge
from hardware_interface.stm32_bridge import STM32Bridge
from hardware_interface.pixhawk_bridge import PixhawkBridge
from vision.vision_processor import VisionProcessor
from utils.ship_logger import ShipLogger
from core.failsafe import FailsafeManager
from core.mission_manager import MissionManager
from controls.motion_controller import MotionController


def load_config():
    config_path = os.path.join(ship_system_root, "config", "low_level_config_remote.yaml")
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[MAIN-SHIP] CRITICAL ERROR: Gagal membaca file konfigurasi: {e}")
        sys.exit(1)


def main():
    print("[MAIN-SHIP] Memulai Orkestrasi Sistem ROV Almasena Candrassa (Modular Architecture)...")

    # 1. Inisialisasi Utilities & Managers
    logger = ShipLogger(max_logs=15)
    failsafe = FailsafeManager(timeout_threshold=1.0)
    mission = MissionManager()
    motion = MotionController(max_encoder_tick=10000.0)

    logger.push("Sistem ROV Almasena Inisialisasi...", "sys")

    # 2. Load Config & Connect Hardware Interface
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
        logger.push("WARN: STM32 tidak terdeteksi!", "warn")

    if pixhawk.connect():
        logger.push("Pixhawk 4 Terhubung & Arming Ready.", "sys")
    else:
        logger.push("WARN: Pixhawk gagal terhubung!", "warn")

    if vision.init_model():
        vision.start_cameras()
        logger.push("AI YOLOv8 Engine Active.", "sys")
    else:
        logger.push("WARN: Engine AI Gagal!", "warn")

    loop_interval = 0.05  # 20Hz Loop Rate
    logger.push("Memasuki Deterministic Orchestrator Loop (~20Hz)", "sys")

    try:
        while True:
            loop_start = time.time()

            # 1. Pembacaan Seluruh Hardware & Network Data
            sensor_data = stm32.get_latest_sensors()
            attitude_data = pixhawk.get_latest_attitude()
            vision_data = vision.get_latest_vision()
            gcs_commands = net.receive_commands()

            current_depth = attitude_data.get("depth_raw", 0.0)

            # 2. Evaluasi Keamanan / Failsafe
            software_kill_active = failsafe.update(gcs_commands, logger, pixhawk)

            # 3. Evaluasi State Mesin Misi (Manual vs Otonom)
            cmds = mission.update(
                gcs_commands=gcs_commands,
                vision_data=vision_data,
                current_depth=current_depth,
                software_kill_active=software_kill_active,
                logger=logger
            )

            # 4. Kalkulasi Kendali Motor & Eksekusi Hardware
            motion_telemetry = motion.process_and_send(
                cmds=cmds,
                sensor_data=sensor_data,
                attitude_data=attitude_data,
                software_kill_active=software_kill_active,
                stm32=stm32,
                pixhawk=pixhawk,
                logger=logger
            )

            # 5. Satukan Seluruh Telemetri & Tembakkan Kembali ke GCS
            combined_telemetry = {
                **sensor_data,
                **attitude_data,
                **motion_telemetry,
                "software_kill_active": software_kill_active,
                "autonomous_active": cmds["is_autonomous"],
                "auto_phase": cmds["auto_phase"],
                "ship_logs": logger.get_logs()
            }

            net.transmit_ship_status(raw_sensor_data=combined_telemetry, vision_data=vision_data)

            # 6. Pengaturan Interval Loop (20Hz)
            elapsed_time = time.time() - loop_start
            time.sleep(max(0, loop_interval - elapsed_time))

    except KeyboardInterrupt:
        print("\n[MAIN-SHIP] Mematikan sistem via KeyboardInterrupt...")
    finally:
        logger.push("Shutdown Sistem ROV Almasena...", "sys")
        vision.stop()
        pixhawk.close()
        stm32.close()
        net.close()
        print("[MAIN-SHIP] Seluruh modul resmi dimatikan secara bersih.")


if __name__ == "__main__":
    main()
