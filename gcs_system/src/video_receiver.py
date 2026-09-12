import cv2
import socket
import threading
import numpy as np
import time
import os
import sys
from datetime import datetime

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

        # State Perekaman Video MP4
        self.is_recording = False
        self.current_record_dir = None
        self.video_writers = {
            "front": None,
            "bottom": None
        }
        self.writer_locks = {
            "front": threading.Lock(),
            "bottom": threading.Lock()
        }

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

    def start_recording(self, target_session_dir: str):
        """Mengaktifkan perekaman video dual kamera ke folder sesi target"""
        with self.memory_lock:
            self.current_record_dir = target_session_dir
            os.makedirs(self.current_record_dir, exist_ok=True)
            self.is_recording = True
        print(f"[GCS-RECORDER] Perekaman MP4 Dual-Cam dimulai di: {target_session_dir}")

    def stop_recording(self):
        """Menghentikan perekaman dan me-release file MP4 secara aman"""
        self.is_recording = False
        time.sleep(0.05)  # Beri jeda kecil agar frame terakhir selesai ditulis

        for cam_key in ["front", "bottom"]:
            with self.writer_locks[cam_key]:
                writer = self.video_writers[cam_key]
                if writer is not None:
                    writer.release()
                    self.video_writers[cam_key] = None
        print("[GCS-RECORDER] Seluruh file rekaman MP4 resmi ditutup dan disimpan.")

    def take_screenshot(self, target_dir: str):
        """Menyimpan frame mentah OpenCV saat ini ke disk sebagai PNG"""
        os.makedirs(target_dir, exist_ok=True)
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_paths = []

        with self.memory_lock:
            f_front = self.shared_frames["front"].copy() if self.shared_frames["front"] is not None else None
            f_bottom = self.shared_frames["bottom"].copy() if self.shared_frames["bottom"] is not None else None

        if f_front is not None:
            path_f = os.path.join(target_dir, f"snap_front_{ts_str}.png")
            cv2.imwrite(path_f, f_front)
            saved_paths.append(path_f)

        if f_bottom is not None:
            path_b = os.path.join(target_dir, f"snap_bottom_{ts_str}.png")
            cv2.imwrite(path_b, f_bottom)
            saved_paths.append(path_b)

        return saved_paths

    def _receiver_worker(self, port, camera_key):
        """Worker internal untuk menangkap paket UDP, decoding, dan menulis ke MP4"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', port))
        sock.settimeout(1.0)

        last_decode_time = 0.0

        while self.is_running:
            try:
                data, addr = sock.recvfrom(65535)
                np_arr = np.frombuffer(data, dtype=np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                if frame is not None:
                    # 1. Perekaman MP4 jika status aktif
                    if self.is_recording and self.current_record_dir:
                        with self.writer_locks[camera_key]:
                            if self.video_writers[camera_key] is None:
                                h, w = frame.shape[:2]
                                out_path = os.path.join(self.current_record_dir, f"{camera_key}.mp4")
                                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                                self.video_writers[camera_key] = cv2.VideoWriter(out_path, fourcc, 20.0, (w, h))

                            self.video_writers[camera_key].write(frame)

                    # 2. Decoding QR
                    if time.time() - last_decode_time > 0.2:
                        last_decode_time = time.time()
                        decoded_objects = decode(frame)

                        with self.memory_lock:
                            if decoded_objects:
                                obj = decoded_objects[0]
                                qr_string = obj.data.decode('utf-8')
                                rect = obj.rect
                                frame_height, frame_width = frame.shape[:2]

                                self.qr_state["qr_data"] = qr_string
                                self.qr_state["qr_camera"] = camera_key
                                self.qr_state["qr_bbox"] = [
                                    rect.left / frame_width,
                                    rect.top / frame_height,
                                    rect.width / frame_width,
                                    rect.height / frame_height
                                ]
                                self.last_qr_time = time.time()
                            else:
                                if self.qr_state["qr_camera"] == camera_key or self.qr_state["qr_camera"] == "":
                                    if time.time() - self.last_qr_time > 1.0:
                                        self.qr_state["qr_data"] = ""
                                        self.qr_state["qr_bbox"] = []
                                        self.qr_state["qr_camera"] = ""

                    # 3. Simpan ke shared memory
                    with self.memory_lock:
                        self.shared_frames[camera_key] = frame

            except socket.timeout:
                continue
            except Exception as e:
                print(f"[GCS-VIDEO-ERROR] Gagal membaca port {port}: {e}")
                break

        sock.close()

    def get_latest_frames(self):
        with self.memory_lock:
            frame_front = self.shared_frames["front"].copy() if self.shared_frames["front"] is not None else None
            frame_bottom = self.shared_frames["bottom"].copy() if self.shared_frames["bottom"] is not None else None
        return frame_front, frame_bottom

    def get_qr_state(self):
        with self.memory_lock:
            return self.qr_state.copy()

    def stop(self):
        self.stop_recording()
        self.is_running = False
        try:
            self.thread_front.join(timeout=1.0)
            self.thread_bottom.join(timeout=1.0)
        except Exception:
            pass
        print("[GCS-VIDEO] Seluruh pipa penerima video resmi ditutup.")
