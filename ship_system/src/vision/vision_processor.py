# almasena-dev/ship_system/src/vision/vision_processor.py

import cv2
import socket
import threading
import time
import os

class VisionProcessor:
    def __init__(self, model_path, gcs_ip, port_front, port_bottom, cam_front_idx="/dev/cam_front", cam_bottom_idx="/dev/cam_bottom"):
        self.model_path = model_path
        self.gcs_ip = gcs_ip
        self.addr_front = (gcs_ip, port_front)
        self.addr_bottom = (gcs_ip, port_bottom)

        self.cam_front_idx = cam_front_idx
        self.cam_bottom_idx = cam_bottom_idx

        # Inisialisasi Soket UDP khusus Video Streaming
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Inisialisasi QR Code Detector bawaan OpenCV
        self.qr_detector = cv2.QRCodeDetector()

        # Thread Management & Shared Memory
        self.is_running = False
        self.latest_data = {
            "front_detected": False,
            "front_bbox": [0, 0, 0, 0],
            "front_qr_data": "",
            "front_qr_bbox": [],

            "bottom_detected": False,
            "bottom_bbox": [0, 0, 0, 0],
            "bottom_qr_data": "",
            "bottom_qr_bbox": []
        }

    def init_model(self):
        """Validasi kesiapan modul visi"""
        print(f"[VISION-YOLO] Memuat arsitektur model dari: {self.model_path}")
        return True

    def _stream_logic(self, cam_path, destination_addr, is_front_cam=True):
        """Worker thread untuk mengurus satu kamera: Baca -> Proses QR -> Kirim UDP"""
        
        # LANGSUNG BUKA MENGGUNAKAN STRING PATH SYMLINK (Tanpa di-resolve ke Index Angka)
        cap = cv2.VideoCapture(cam_path, cv2.CAP_V4L2)

        # Config camera hardware (Disesuaikan ke max 720p agar C270 tidak crash)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 15)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)

        if not cap.isOpened():
            print(f"[VISION-ENGINE] ERROR: Gagal membuka kamera pada path {cam_path}!")
            return
        else:
            print(f"[VISION-ENGINE] SUKSES: Kamera {cam_path} berhasil dibuka.")

        last_qr_check = 0.0
        cam_label = "FRONT" if is_front_cam else "BOTTOM"
        prefix = "front" if is_front_cam else "bottom"

        while self.is_running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            # --- 1. PROSES MEMBACA QR CODE ---
            current_time = time.time()
            if current_time - last_qr_check > 0.5:
                last_qr_check = current_time

                data, bbox, _ = self.qr_detector.detectAndDecode(frame)
                if bbox is not None and len(data) > 0:
                    qr_points = bbox.astype(int).reshape(-1, 2)
                    x, y, w, h = cv2.boundingRect(qr_points)

                    self.latest_data[f"{prefix}_detected"] = True
                    self.latest_data[f"{prefix}_bbox"] = [x + w//2, y + h//2, w, h]
                    self.latest_data[f"{prefix}_qr_data"] = data
                    frame_height, frame_width = frame.shape[:2]
                    self.latest_data[f"{prefix}_qr_bbox"] = [
                        x / frame_width,
                        y / frame_height,
                        w / frame_width,
                        h / frame_height
                    ]

                    print(f"[{cam_label}-QR INTERCEPT] Terdeteksi String: '{data}' | Bbox Center: [{x + w//2}, {y + h//2}]")
                else:
                    self.latest_data[f"{prefix}_detected"] = False

            # --- 2. KOMPRESI GAMBAR & KIRIM VIA UDP ---
            stream_frame = cv2.resize(frame, (640, 360))
            ret_encode, encoded_img = cv2.imencode('.jpg', stream_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 40])
            if ret_encode:
                bytes_data = encoded_img.tobytes()
                if len(bytes_data) < 61000:
                    try:
                        self.sock.sendto(bytes_data, destination_addr)
                    except Exception:
                        pass

            time.sleep(0.03)

        cap.release()

    def start_cameras(self):
        """Menyalakan pipa streaming kedua kamera secara paralel"""
        self.is_running = True
        print("[VISION-ENGINE] Pipa pengaliran data & Dual QR Scanner resmi berjalan aktif.")

        self.thread_front = threading.Thread(target=self._stream_logic, args=(self.cam_front_idx, self.addr_front, True))
        self.thread_bottom = threading.Thread(target=self._stream_logic, args=(self.cam_bottom_idx, self.addr_bottom, False))

        self.thread_front.daemon = True
        self.thread_bottom.daemon = True

        self.thread_front.start()
        self.thread_bottom.start()

    def get_latest_vision(self):
        """Membaca status target otonom terbaru"""
        combined_data = self.latest_data.copy()

        if combined_data["bottom_detected"]:
            combined_data["target_detected"] = True
            combined_data["bbox"] = combined_data["bottom_bbox"]
            combined_data["qr_data"] = combined_data["bottom_qr_data"]
            combined_data["qr_camera"] = "bottom"
            combined_data["qr_bbox"] = combined_data["bottom_qr_bbox"]
        elif combined_data["front_detected"]:
            combined_data["target_detected"] = True
            combined_data["bbox"] = combined_data["front_bbox"]
            combined_data["qr_data"] = combined_data["front_qr_data"]
            combined_data["qr_camera"] = "front"
            combined_data["qr_bbox"] = combined_data["front_qr_bbox"]
        else:
            combined_data["target_detected"] = False
            combined_data["bbox"] = [0, 0, 0, 0]
            combined_data["qr_data"] = ""
            combined_data["qr_camera"] = ""
            combined_data["qr_bbox"] = []

        return combined_data

    def stop(self):
        """Mematikan seluruh thread secara bersih"""
        self.is_running = False
        try:
            self.thread_front.join(timeout=1.0)
            self.thread_bottom.join(timeout=1.0)
        except Exception:
            pass
        self.sock.close()
        print("[VISION-ENGINE] Seluruh pipa pemrosesan gambar ditutup secara bersih.")
