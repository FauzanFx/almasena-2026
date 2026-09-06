# ~/almasena-dev/gcs_system/src/video_receiver.py

import cv2
import socket
import threading
import numpy as np
import time
import sys

# Pengecekan Dependency PyZbar
try:
    from pyzbar.pyzbar import decode
except ImportError:
    print("\n[GCS-CRITICAL] Library 'pyzbar' tidak ditemukan!")
    print("Harap install dengan: pip install pyzbar")
    print("(Catatan: Di Linux pastikan library 'zbar-tools' atau 'libzbar0' juga terinstall di OS)\n")
    sys.exit(1)

class VideoReceiver:
    def __init__(self, port_front=5000, port_bottom=5001):
        self.port_front = port_front
        self.port_bottom = port_bottom

        # Shared memory untuk frame terakhir
        self.shared_frames = {
            "front": None,
            "bottom": None
        }

        # State QR hasil decode GCS
        self.qr_state = {
            "qr_data": "",
            "qr_camera": "",
            "qr_bbox": []
        }
        self.last_qr_time = 0.0

        self.memory_lock = threading.Lock()
        self.is_running = False

    def start(self):
        """Menyalakan thread penerima video di background"""
        self.is_running = True

        self.thread_front = threading.Thread(target=self._receiver_worker, args=(self.port_front, "front"))
        self.thread_bottom = threading.Thread(target=self._receiver_worker, args=(self.port_bottom, "bottom"))

        self.thread_front.daemon = True
        self.thread_bottom.daemon = True

        self.thread_front.start()
        self.thread_bottom.start()
        print(f"[GCS-VIDEO] Modul penerima & QR Decoder aktif (Port: {self.port_front}, {self.port_bottom})")

    def _receiver_worker(self, port, camera_key):
        """Worker internal untuk menangkap paket UDP & men-decode JPEG"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', port))
        sock.settimeout(1.0)

        # Timer internal thread untuk membatasi laju decode (opsional, menghemat CPU GCS)
        last_decode_time = 0.0

        while self.is_running:
            try:
                data, addr = sock.recvfrom(65535)
                np_arr = np.frombuffer(data, dtype=np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                if frame is not None:
                    # Injeksi Decoding QR untuk KEDUA kamera
                    if time.time() - last_decode_time > 0.2:
                        last_decode_time = time.time()
                        decoded_objects = decode(frame)

                        with self.memory_lock:
                            if decoded_objects:
                                obj = decoded_objects[0]
                                qr_string = obj.data.decode('utf-8')
                                rect = obj.rect
                                frame_height, frame_width = frame.shape[:2]

                                # Format normalisasi: x_norm, y_norm, w_norm, h_norm
                                self.qr_state["qr_data"] = qr_string
                                self.qr_state["qr_camera"] = camera_key  # Dinamis: mencatat kamera mana yang mendeteksi
                                self.qr_state["qr_bbox"] = [
                                    rect.left / frame_width,
                                    rect.top / frame_height,
                                    rect.width / frame_width,
                                    rect.height / frame_height
                                ]
                                self.last_qr_time = time.time()
                            else:
                                # Pengaman: Hanya izinkan kamera penemu (atau jika kosong) yang bisa mereset state
                                # agar kamera depan & bawah tidak saling hapus data.
                                if self.qr_state["qr_camera"] == camera_key or self.qr_state["qr_camera"] == "":
                                    if time.time() - self.last_qr_time > 1.0:
                                        self.qr_state["qr_data"] = ""
                                        self.qr_state["qr_bbox"] = []
                                        self.qr_state["qr_camera"] = ""

                    # Simpan frame ke shared memory
                    with self.memory_lock:
                        self.shared_frames[camera_key] = frame

            except socket.timeout:
                continue
            except Exception as e:
                print(f"[GCS-VIDEO-ERROR] Gagal membaca port {port}: {e}")
                break

        sock.close()

    def get_latest_frames(self):
        """Dipanggil oleh main thread untuk mengambil duplikasi frame terbaru secara aman"""
        with self.memory_lock:
            frame_front = self.shared_frames["front"].copy() if self.shared_frames["front"] is not None else None
            frame_bottom = self.shared_frames["bottom"].copy() if self.shared_frames["bottom"] is not None else None
        return frame_front, frame_bottom

    def get_qr_state(self):
        """Dipanggil oleh main thread untuk mengambil status QR"""
        with self.memory_lock:
            return self.qr_state.copy()

    def stop(self):
        """Mematikan seluruh thread jaringan video secara bersih"""
        self.is_running = False
        try:
            self.thread_front.join(timeout=1.0)
            self.thread_bottom.join(timeout=1.0)
        except Exception:
            pass
        print("[GCS-VIDEO] Seluruh pipa penerima video resmi ditutup.")
