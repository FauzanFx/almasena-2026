import os
import sys
import time
import json
import math
import yaml
from pathlib import Path
from datetime import datetime

# Setup Path Modul
current_file = Path(__file__).resolve()
ship_system_root = current_file.parents[1]
sys.path.append(os.path.join(ship_system_root, "src"))

from network.net_bridge import NetBridge
from hardware_interface.stm32_bridge import STM32Bridge
from hardware_interface.pixhawk_bridge import PixhawkBridge
from vision.vision_processor import VisionProcessor
from utils.ship_logger import ShipLogger
from core.failsafe import FailsafeManager
from core.mission_manager import MissionManager
from controls.motion_controller import MotionController


def load_config():
    config_path = os.path.join(ship_system_root, "config", "low_level_config.yaml")
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[MAIN-SHIP] CRITICAL ERROR: Gagal membaca file konfigurasi: {e}")
        sys.exit(1)


def main():
    print("[MAIN-SHIP] Memulai Orkestrasi Sistem ROV Almasena Candrassa...")

    logger = ShipLogger(max_logs=15)
    failsafe = FailsafeManager(timeout_threshold=1.0)
    mission = MissionManager()
    motion = MotionController()

    logger.push("Sistem ROV Almasena Inisialisasi...", "sys")

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

    if stm32.connect():
        print(f"[STM32-BALLAST] Terhubung ke STM32 via {stm32.port}!")
    else:
        print(f"[STM32-BALLAST] ERROR: Gagal terhubung ke STM32 via {hw_cfg['stm32_port']}!")

    if pixhawk.connect():
        pass
    if vision.init_model():
        vision.start_cameras()

    pos_x = 0.0
    pos_y = 0.0
    last_odom_time = time.time()
    SURGE_VELOCITY_MAX = 0.4

    # Blackbox Logger

    log_dir = os.path.join(ship_system_root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    mission_log_file = os.path.join(log_dir, f"blackbox_trajectory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")
    log_handle = open(mission_log_file, "a", buffering=1)
    last_blackbox_save = time.time()

    loop_interval = 0.05
    last_debug_print = time.time()

    try:
        print("\n")

        while True:
            loop_start = time.time()

            sensor_data = stm32.get_latest_sensors()
            attitude_data = pixhawk.get_latest_attitude()
            vision_data = vision.get_latest_vision()
            gcs_commands = net.receive_commands() or {}
            current_depth = attitude_data.get("depth_raw", 0.0)

            # Kalkulasi Dead Reckogning (X, Y)
            dt = loop_start - last_odom_time
            last_odom_time = loop_start

            cur_hdg_deg = attitude_data.get("heading", 0.0)
            cur_hdg_rad = math.radians(cur_hdg_deg)
            srg_input = gcs_commands.get("surge", 0)
            v_est = (srg_input / 1000.0) * SURGE_VELOCITY_MAX

            # Dead-reckoning integration saat ada daya dorong
            if abs(v_est) > 0.05:
                pos_x += v_est * math.cos(cur_hdg_rad) * dt
                pos_y += v_est * math.sin(cur_hdg_rad) * dt

            # Prioritaskan koordinat hardware/MAVLink jika ada, fallback ke kalkulasi lokal
            final_x = attitude_data.get("pos_x", 0.0) or round(pos_x, 3)
            final_y = attitude_data.get("pos_y", 0.0) or round(pos_y, 3)
            is_armed = pixhawk.get_arm_status()

            software_kill_active = failsafe.update(gcs_commands, logger, pixhawk)

            cmds = mission.update(
                gcs_commands=gcs_commands, vision_data=vision_data,
                current_depth=current_depth, software_kill_active=software_kill_active,
                logger=logger
            )
            cmds["zero_encoder"] = gcs_commands.get("zero_encoder", False)
            cmds["max_encoder"] = gcs_commands.get("max_encoder", False)

            motion_telemetry = motion.process_and_send(
                cmds=cmds, sensor_data=sensor_data, attitude_data=attitude_data,
                software_kill_active=software_kill_active, stm32=stm32,
                pixhawk=pixhawk, logger=logger
            )

            if loop_start - last_blackbox_save >= 0.2:
                blackbox_entry = {
                    "ts": round(loop_start, 2),
                    "x": final_x,
                    "y": final_y,
                    "depth": round(current_depth, 2),
                    "heading": round(cur_hdg_deg, 1),
                    "armed": is_armed,
                    "surge": srg_input
                }
                log_handle.write(json.dumps(blackbox_entry) + "\n")
                last_blackbox_save = loop_start

            if loop_start - last_debug_print > 0.1:
                srg = gcs_commands.get('surge', 0)
                yw = gcs_commands.get('yaw', 0)
                pch = gcs_commands.get('pitch', 0)
                blst = gcs_commands.get('ballast_cmd', 0)
                grp = gcs_commands.get('gripper_cmd', 0)
                z_cmd = gcs_commands.get('zero_encoder', False)
                m_cmd = gcs_commands.get('max_encoder', False)

                t_enc = sensor_data.get('encoder_ticks', 0)
                t_tgt = sensor_data.get('target_stm32', 0)
                t_pwm = sensor_data.get('pwm_stm32', 0)

                cur_pch = attitude_data.get("pitch", 0.0)
                p_status = "HOLD" if motion_telemetry.get("pitch_hold", False) else "MAN"
                h_status = "HOLD" if motion_telemetry.get("heading_hold", False) else "MAN"
                arm_str = "ARM" if is_armed else "DISARM"

                # Cetak baris NET-RX
                print(f"\r\033[K[NET-RX LIVE] Srg:{srg:4} | Yaw:{yw:5} | Pch:{pch:5} | Bal:{blst:3} | Grp:{grp:2} | [{arm_str}] | Pos:({final_x:.1f},{final_y:.1f}) | IMU Hdg:{cur_hdg_deg:5.1f}° [{h_status}] | Pch:{cur_pch:5.1f}° [{p_status}]")

                last_debug_print = loop_start

            combined_telemetry = {
                **sensor_data, **attitude_data, **motion_telemetry,
                "pos_x": final_x,
                "pos_y": final_y,
                "is_armed": is_armed,
                "software_kill_active": software_kill_active,
                "autonomous_active": cmds.get("is_autonomous", False),
                "auto_phase": cmds.get("auto_phase", "MANUAL"),
                "ship_logs": logger.get_logs()
            }

            net.transmit_ship_status(raw_sensor_data=combined_telemetry, vision_data=vision_data)

            elapsed_time = time.time() - loop_start
            time.sleep(max(0, loop_interval - elapsed_time))

    except KeyboardInterrupt:
        print("\n\n[MAIN-SHIP] Mematikan sistem...")
    finally:
        if 'log_handle' in locals() and not log_handle.closed:
            log_handle.close()
        vision.stop()
        pixhawk.close()
        stm32.close()
        net.close()


if __name__ == "__main__":
    main()
