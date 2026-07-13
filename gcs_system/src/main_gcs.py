# almasena-dev/gcs_system/src/main_gcs.py

import sys
import os
import time
import cv2

# Pastikan Python mengenali direktori src saat dieksekusi
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from net_handler import NetHandler
from input_handler import InputHandler
from video_receiver import VideoReceiver  # Modul video streaming terpisah kita

def main():
    print("[MAIN-GCS] Memulai Ground Control Station ROV Almasena...")

    # 1. Inisialisasi Modul Input Gamepad, Jaringan UDP, dan Modular Video Streaming
    input_manager = InputHandler()
    net_manager = NetHandler(rov_ip="192.168.1.20", send_port=5005, recv_port=5006)

    # Panggil engine video penerima tanpa mengganggu pipeline data stik/telemetri
    video_engine = VideoReceiver(port_front=5000, port_bottom=5001)
    video_engine.start()

    # 2. Penguncian Frekuensi Perulangan Loop
    loop_interval = 0.05
    print("[MAIN-GCS] Sistem siap. Memasuki Perulangan GCS Loop Terintegrasi Video.")
    print("Tekan Ctrl+C atau tombol 'q' pada jendela video untuk menghentikan GCS.")
    print("-" * 85)

    try:
        while True:
            loop_start = time.time()

            # 1. Baca Input dan Kirim Command
            commands = input_manager.get_commands()

            net_manager.send_commands_to_rov(commands)

            # 2. Menerima data Telemetry dari ROV
            telemetry = net_manager.receive_telemetry_from_rov()

            # Ekstrak data telemetri dengan nilai default jika data belum masuk (None)
            rov_mode = telemetry.get('auto_phase', 'MANUAL') if telemetry else 'MANUAL'
            rov_depth = telemetry.get('depth_raw', 0.0) if telemetry else 0.0
            rov_volt = telemetry.get('voltage_raw', 0.0) if telemetry else 0.0
            rov_leak = 'AMAN' if (telemetry and not telemetry.get('leak_status', False)) else 'DISCONNECT'
            rov_ai = 'TERKUNCI' if (telemetry and telemetry.get('autonomous_active', False)) else 'MENCARI'

            # 3. Membaca Frame Video dari Kamera Raspi
            frame_front, frame_bottom = video_engine.get_latest_frames()

            if frame_front is not None:
                # Kita bisa sisipkan info telemetri ROV langsung di atas gambar kamera depan!
                cv2.putText(frame_front, f"AI TARGET: {rov_ai}", (10, 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                cv2.imshow("GCS Feed - Kamera Depan", frame_front)

            if frame_bottom is not None:
                cv2.putText(frame_bottom, f"AI TARGET: {rov_ai}", (10, 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                cv2.imshow("GCS Feed - Kamera Bawah", frame_bottom)

            # 4. Tampilan HUD
            ballast_map = {1: "MENGISI", -1: "MENGELUARKAN"}
            gripper_map = {1: "MELEPASKAN", -1: "MENJEPIT"}
            ballast_status = ballast_map.get(commands["ballast_cmd"], "IDLE")
            gripper_status = gripper_map.get(commands["gripper_cmd"], "IDLE")
            log_msg = (
                f"\r[GCS-LIVE] "
                f"Surge: {commands['surge']:4d} | "
                f"Yaw: {commands['yaw']:4d} | "
                f"Heave: {commands['heave']:4d} | "
                f"Ballast: {ballast_status} | "
                f"Grip: {gripper_status} | "
                f"Auto-Sw: {str(commands['autonomous_mode']):5s} || "
                f"ROV -> Mode: {rov_mode:7s} | Depth: {rov_depth:.2f}m | Volt: {rov_volt:.1f}V | Leak: {rov_leak:10s}"
            )
            sys.stdout.write(log_msg)
            sys.stdout.flush()

            # 5. Time Control dan Refresh Event
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("\n[MAIN-GCS] Instruksi penutupan sistem diterima dari keyboard window.")
                break

            elapsed_time = time.time() - loop_start
            time.sleep(max(0, loop_interval - elapsed_time))

    except KeyboardInterrupt:
        print("\n\n[MAIN-GCS] Menerima instruksi interupsi keyboard. Mematikan GCS...")
    finally:
        print("\n[MAIN-GCS] Menutup seluruh subsistem darat...")
        # Bersihkan soket video, tutup window grafik, baru matikan net_manager asli lu
        video_engine.stop()
        cv2.destroyAllWindows()
        net_manager.close()
        print("[MAIN-GCS] Aplikasi darat berhasil ditutup dengan aman. Safe dive!")

if __name__ == "__main__":
    main()
