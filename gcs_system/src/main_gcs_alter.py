# almasena-dev/gcs_system/src/main_gcs_alter.py

import os
import sys
import time
import cv2

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from net_handler import NetHandler
from input_handler import InputHandler
from video_receiver import VideoReceiver
from gui_bridge import GUIBridge


def main():
    print("[MAIN-GCS] Memulai Orchestrator ROV Almasena GCS...")

    net_manager = NetHandler(rov_ip="192.168.1.20", send_port=5005, recv_port=5006)
    input_manager = InputHandler()

    video_engine = VideoReceiver(port_front=5000, port_bottom=5001)
    video_engine.start()

    gui = GUIBridge(host="0.0.0.0", port=8000)
    gui.set_video_engine(video_engine)

    def handle_gui_control(cmd_data):
        net_manager.send_commands_to_rov(cmd_data)

    gui.set_control_callback(handle_gui_control)
    gui.start_in_thread()

    loop_interval = 0.05  # Loop 20Hz (~50ms)
    last_telemetry_time = 0.0

    # State Data Terakumulasi
    gcs_state = {
        "ping_ms": 0,
        "surge_cmd": 0,
        "pitch_cmd": 0,
	"yaw_cmd": 0,
        "autonomous_active": False,
        "roll": 0.0,
        "pitch": 0.0,
        "depth_raw": 0.0,
        "heading": 0.0,
        "ballast_pct": 0,
        "ballast_status": "IDLE",
        "ship_logs": [],
        "qr_data": ""
    }

    print("[MAIN-GCS] Dashboard Aktif: http://localhost:8000")
    print("=" * 80)

    try:
        while True:
            loop_start = time.time()
            now = time.time()

            # 1. BACA LANGSUNG INPUT JOYSTICK DARI INPUT_HANDLER
            cmds = input_manager.get_commands()
            if cmds:
                # Kirim ke Raspi via UDP
                net_manager.send_commands_to_rov(cmds)

                # Ekstrak langsung key resmi dari InputHandler
                gcs_state["surge_cmd"] = cmds.get("surge", 0)
                gcs_state["pitch_cmd"] = cmds.get("pitch", 0)
                gcs_state["yaw_cmd"] = cmds.get("yaw", 0)
                gcs_state["autonomous_active"] = cmds.get("autonomous_mode", False)

            # 2. TERIMA TELEMETRI DARI RASPI
            telemetry = net_manager.receive_telemetry_from_rov()

            if telemetry:
                # Hitung interval waktu terima paket UDP (Ping Latency dalam ms)
                if last_telemetry_time > 0:
                    delta_ms = int((now - last_telemetry_time) * 1000)
                    gcs_state["ping_ms"] = max(1, min(999, delta_ms))
                else:
                    gcs_state["ping_ms"] = 1

                last_telemetry_time = now

                # Parsing data sensor dari Raspi
                sensors = telemetry.get("sensors", telemetry) if isinstance(telemetry, dict) else {}
                if isinstance(sensors, dict):
                    gcs_state["roll"] = float(sensors.get("roll", 0.0))
                    gcs_state["pitch"] = float(sensors.get("pitch", 0.0))
                    gcs_state["depth_raw"] = float(sensors.get("depth_raw", sensors.get("depth", 0.0)))
                    gcs_state["heading"] = float(sensors.get("heading", sensors.get("hdg", 0.0)))
                    gcs_state["ballast_pct"] = int(sensors.get("ballast_pct", 0))
                    gcs_state["ballast_status"] = sensors.get("ballast_status", "IDLE")

                # --- PERBAIKAN MISSION LOG DI SINI ---
                # Cek ship_logs baik di dalam "sensors" maupun di luar root telemetry
                if isinstance(sensors, dict) and "ship_logs" in sensors:
                    gcs_state["ship_logs"] = sensors["ship_logs"]
                elif isinstance(telemetry, dict) and "ship_logs" in telemetry:
                    gcs_state["ship_logs"] = telemetry["ship_logs"]

                # Hasil QR dari VisionProcessor dikirim pada objek telemetry.vision.
                vision = telemetry.get("vision", {}) if isinstance(telemetry, dict) else {}
                if isinstance(vision, dict):
                    gcs_state["qr_data"] = vision.get("qr_data", "")
                # -------------------------------------
            else:
                # Jika tidak ada data telemetri > 1.5 detik, set ping ke 0 (Offline)
                if last_telemetry_time > 0 and (now - last_telemetry_time) > 1.5:
                    gcs_state["ping_ms"] = 0

            # 3. SIARKAN KE WEBSOCKET BROWSER SETIAP ITERASI LOOP (20Hz)
            gui.broadcast_telemetry(gcs_state)

            # 4. PREVIEW VIDEO OPENCV
            frame_front, frame_bottom = video_engine.get_latest_frames()
            if frame_front is not None:
                cv2.imshow("GCS Feed - Kamera Depan", frame_front)
            if frame_bottom is not None:
                cv2.imshow("GCS Feed - Kamera Bawah", frame_bottom)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            elapsed_time = time.time() - loop_start
            time.sleep(max(0, loop_interval - elapsed_time))

    except KeyboardInterrupt:
        print("\n[MAIN-GCS] Mematikan GCS...")
    finally:
        video_engine.stop()
        cv2.destroyAllWindows()
        net_manager.close()


if __name__ == "__main__":
    main()
