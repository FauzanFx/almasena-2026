# almasena-dev/gcs_system/src/main_gcs.py

import sys
import os
import time

# Pastikan Python mengenali direktori src saat dieksekusi
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from net_handler import NetHandler
from input_handler import InputHandler

def main():
    print("[MAIN-GCS] Memulai Ground Control Station ROV Almasena...")

    # 1. Inisialisasi Modul Input Gamepad dan Jaringan UDP
    # Ubah ke "127.0.0.1" jika tes lokal satu laptop, atau sesuaikan IP Raspi kapal nanti
    input_manager = InputHandler()
    net_manager = NetHandler(rov_ip="192.168.1.20", send_port=5005, recv_port=5006)

    # 2. Penguncian Frekuensi Perulangan Loop (~20Hz / 50 milidetik)
    loop_interval = 0.1
    print("[MAIN-GCS] Sistem siap. Memasuki Perulangan Headless GCS Loop (~20Hz).")
    print("Tekan Ctrl+C untuk menghentikan GCS.")
    print("-" * 85)

    try:
        while True:
            loop_start = time.time()

            # ---------------------------------------------------------------
            # TAHAP 1: BACA INPUT & KIRIM KOMANDO KE ROV
            # ---------------------------------------------------------------
            commands = input_manager.get_commands()

            # Tembakkan langsung menembus kabel LAN ke kapal
            net_manager.send_commands_to_rov(commands)

            # ---------------------------------------------------------------
            # TAHAP 2: TERIMA TELEMETRI DARI ROV
            # ---------------------------------------------------------------
            telemetry = net_manager.receive_telemetry_from_rov()

            # Ekstrak data telemetri dengan nilai default jika data belum masuk (None)
            rov_mode = telemetry.get('auto_phase', 'MANUAL') if telemetry else 'MANUAL'
            rov_depth = telemetry.get('depth_raw', 0.0) if telemetry else 0.0
            rov_volt = telemetry.get('voltage_raw', 0.0) if telemetry else 0.0
            rov_leak = 'AMAN' if (telemetry and not telemetry.get('leak_status', False)) else 'DISCONNECT'
            rov_ai = 'TERKUNCI' if (telemetry and telemetry.get('autonomous_active', False)) else 'MENCARI'

            # ---------------------------------------------------------------
            # TAHAP 3: TAMPILKAN HUD INTEGRASI (STICK LOKAL + TELEMETRI KAPAL)
            # ---------------------------------------------------------------
            # Menggunakan susunan rata kanan/kiri agar angka stik tidak bergeser berantakan
            log_msg = (
                f"\r[GCS-LIVE] "
                f"Surge: {commands['surge']:4d} | "
                f"Yaw: {commands['yaw']:4d} | "
                f"Heave: {commands['heave']:4d} | "
                f"Grip: {commands['gripper_state']} | "
                f"Auto-Sw: {str(commands['autonomous_mode']):5s} || "
                f"ROV -> Mode: {rov_mode:7s} | Depth: {rov_depth:.2f}m | Volt: {rov_volt:.1f}V | Leak: {rov_leak:10s}"
            )
            
            sys.stdout.write(log_msg)
            sys.stdout.flush()

            # ---------------------------------------------------------------
            # TAHAP 4: KONTROL WAKTU (DETERMINISTIK LOOP)
            # ---------------------------------------------------------------
            elapsed_time = time.time() - loop_start
            time.sleep(max(0, loop_interval - elapsed_time))

    except KeyboardInterrupt:
        print("\n\n[MAIN-GCS] Menerima instruksi interupsi keyboard. Mematikan GCS...")
    finally:
        # Bersihkan soket jaringan sebelum keluar dari program
        net_manager.close()
        print("[MAIN-GCS] Aplikasi darat berhasil ditutup dengan aman.")

if __name__ == "__main__":
    main()
