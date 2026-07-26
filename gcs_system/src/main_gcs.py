# almasena-dev/gcs_system/src/main_gcs.py

import sys
import os
import time
import cv2

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from net_handler import NetHandler
from input_handler import InputHandler
from video_receiver import VideoReceiver

def main():
    print("[MAIN-GCS] Memulai Ground Control Station ROV Almasena...")

    input_manager = InputHandler()
    net_manager = NetHandler(rov_ip="192.168.1.20", send_port=5005, recv_port=5006)

    video_engine = VideoReceiver(port_front=5000, port_bottom=5001)
    video_engine.start()

    loop_interval = 0.05
    print("[MAIN-GCS] Sistem siap. Memasuki Perulangan GCS Loop Terintegrasi Video.")
    print("Tekan Ctrl+C or tombol 'q' pada jendela video untuk menghentikan GCS.")
    print("-" * 85)

    try:
        while True:
            loop_start = time.time()

            commands = input_manager.get_commands()
            net_manager.send_commands_to_rov(commands)

            telemetry = net_manager.receive_telemetry_from_rov()

            # --- SINKRONISASI TELEMETRI ASLI DARI RASPI ---
            # Menyesuaikan dengan struktur payload riil dari kapal ('sensors')
            if telemetry and 'sensors' in telemetry:
                ship_data = telemetry.get('sensors', {})
                vision_data = telemetry.get('vision', {})
                
                is_rov_kill = ship_data.get('software_kill_active', False)
                is_rov_auto = ship_data.get('autonomous_active', False)
                phase_rov = ship_data.get('auto_phase', 'MANUAL')

                # Parsing visualisasi status riil hasil konfirmasi balik dari lambung kapal
                rov_kill = 'LOCKED' if is_rov_kill else 'UNLOCKED'
                rov_mode = f"AUTO-{phase_rov}" if is_rov_auto else "MANUAL"

                rov_depth = ship_data.get('depth_raw', 0.0)
                rov_volt = ship_data.get('voltage_raw', 0.0)
                
                # leak_status di log bernilai integer (0 atau 1)
                is_leak = bool(ship_data.get('leak_status', 0))
                rov_leak = 'BOCOR!' if is_leak else 'AMAN'
                
                # Ambil status deteksi AI target dari sub-dict vision
                is_target_found = vision_data.get('target_detected', False)
                rov_ai = 'TERKUNCI' if is_target_found else 'MENCARI'
            else:
                # Jalur fallback jika paket data UDP terputus atau belum masuk
                rov_kill = 'UNKNOWN'
                rov_mode = 'UNKNOWN'
                rov_depth = 0.0
                rov_volt = 0.0
                rov_leak = 'DISCONNECT'
                rov_ai = 'UNKNOWN'

            frame_front, frame_bottom = video_engine.get_latest_frames()

            if frame_front is not None:
                cv2.putText(frame_front, f"AI TARGET: {rov_ai} | SHIP: {rov_kill}", (10, 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                cv2.imshow("GCS Feed - Kamera Depan", frame_front)

            if frame_bottom is not None:
                cv2.putText(frame_bottom, f"AI TARGET: {rov_ai} | SHIP: {rov_kill}", (10, 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                cv2.imshow("GCS Feed - Kamera Bawah", frame_bottom)

            ballast_map = {1: "MENGISI", -1: "MENGELUARKAN"}
            gripper_map = {1: "MELEPASKAN", -1: "MENJEPIT"}
            ballast_status = ballast_map.get(commands["ballast_cmd"], "IDLE")
            gripper_status = gripper_map.get(commands["gripper_cmd"], "IDLE")

            log_msg = (
                f"\r[GCS-LIVE] "
                f"Surge: {commands['surge']:4d} | "
                f"Yaw: {commands['yaw']:4d} | "
                f"Pitch: {commands['pitch']:4d} | "
                f"Ballast: {commands['ballast_cmd']:4d} | "
                f"Pitch-Hold: {str(commands['hold_pitch']):5s} | "
                f"Kill-Stik: {str(commands['kill_switch']):5s} || "
                f"ROV -> State: {rov_kill:8s} | Mode: {rov_mode:12s} | Depth: {rov_depth:.2f}m | Volt: {rov_volt:.1f}V | Leak: {rov_leak:10s}    "
            )
            sys.stdout.write(log_msg)
            sys.stdout.flush()

            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("\n[MAIN-GCS] Profil penutupan sistem diterima dari keyboard window.")
                break

            elapsed_time = time.time() - loop_start
            time.sleep(max(0, loop_interval - elapsed_time))

    except KeyboardInterrupt:
        print("\n\n[MAIN-GCS] Menerima instruksi interupsi keyboard. Mematikan GCS...")
    finally:
        print("\n[MAIN-GCS] Menutup seluruh subsistem darat...")
        video_engine.stop()
        cv2.destroyAllWindows()
        net_manager.close()
        print("[MAIN-GCS] Aplikasi darat berhasil ditutup dengan aman. Safe dive!")

if __name__ == "__main__":
    main()
