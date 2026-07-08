# ~/almasena-dev/gcs_system/src/tes_gcs_stream.py

import cv2
import socket
import numpy as np
import threading
import time

# Shared Memory untuk menampung frame terakhir dari masing-masing kamera
shared_frames = {
    "depan": None,
    "bawah": None
}
memory_lock = threading.Lock()
is_running = True

def video_receiver_worker(port, camera_key):
    """Worker Thread: Murni urusan Jaringan & Decode (Bebas dari GUI)"""
    global is_running
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', port))
    sock.settimeout(1.0)

    print(f"[NET-RX] Thread port {port} stand-by menangkap data...")

    while is_running:
        try:
            data, addr = sock.recvfrom(65535)
            np_arr = np.frombuffer(data, dtype=np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if frame is not None:
                # Kunci memori sesaat untuk update frame terbaru
                with memory_lock:
                    shared_frames[camera_key] = frame

        except socket.timeout:
            continue
        except Exception as e:
            print(f"Error pada port {port}: {e}")
            break

    sock.close()

if __name__ == "__main__":
    print("=== Uji Coba Penerimaan Dual-Kamera ROV Almasena (Thread-Safe) ===")
    
    # 1. Nyalakan penerima jaringan di latar belakang (Background)
    thread_depan = threading.Thread(target=video_receiver_worker, args=(5000, "depan"))
    thread_bawah = threading.Thread(target=video_receiver_worker, args=(5001, "bawah"))
    
    thread_depan.daemon = True
    thread_bawah.daemon = True
    
    thread_depan.start()
    thread_bawah.start()

    print("[GCS-MAIN] GUI Engine aktif di Main Thread. Menunggu data masuk...")

    # 2. Main Thread: Fokus mengurus Rendering GUI & Window
    try:
        while True:
            # Ambil kloningan frame terakhir dengan aman
            with memory_lock:
                frame_depan = shared_frames["depan"].copy() if shared_frames["depan"] is not None else None
                frame_bawah = shared_frames["bawah"].copy() if shared_frames["bawah"] is not None else None

            # Render ke layar jika frame sudah tersedia
            if frame_depan is not None:
                cv2.imshow("Kamera Depan (Port 5000)", frame_depan)
            
            if frame_bawah is not None:
                cv2.imshow("Kamera Bawah (Port 5001)", frame_bawah)

            # Tombol penghenti loop (Tekan 'q' di jendela gambar)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[GCS-MAIN] Menutup aplikasi via instruksi pengguna.")
                break
                
            # Beri jeda mikro agar CPU laptop tidak overload 100%
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n[GCS-MAIN] Menutup aplikasi via Ctrl+C.")
    finally:
        is_running = False
        thread_depan.join(timeout=1.0)
        thread_bawah.join(timeout=1.0)
        cv2.destroyAllWindows()
        print("=== Pipa Penerima Resmi Dimatikan Bersih ===")
