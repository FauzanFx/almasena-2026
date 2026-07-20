# almasena-dev/ship_system/src/vision/vision_processor.py

import cv2
import socket
import threading
import time

class VisionProcessor:
    def __init__(self, model_path, gcs_ip, port_front, port_bottom, cam_front_idx=0, cam_bottom_idx=2):
        self.model_path = model_path
        self.gcs_ip = gcs_ip
        self.addr_front = (gcs_ip, port_front)
        self.addr_bottom = (gcs_ip, port_bottom)

        self.cam_front_idx = cam_front_idx
        self.cam_bottom_idx = cam_bottom_idx

        # Inisialisasi Soket UDP khusus Video Streaming
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Inisialisasi QR Code Detector bawaan OpenCV (Ringan & Instan)
        self.qr_detector = cv2.QRCodeDetector()

        # Thread Management & Shared Memory (Dipisah agar tidak tabrakan antar thread)
        self.is_running = False
        self.latest_data = {
            "front_detected": False,
            "front_bbox": [0, 0, 0, 0],
            "front_qr_data": "",
            
            "bottom_detected": False,
            "bottom_bbox": [0, 0, 0, 0],
            "bottom_qr_data": ""
        }

    def init_model(self):
        """Validasi kesiapan modul visi"""
        print(f"[VISION-YOLO] Memuat arsitektur model dari: {self.model_path}")
        return True

    def _stream_logic(self, cam_idx, destination_addr, is_front_cam=True):
        """Worker thread untuk mengurus satu kamera: Baca -> Proses QR -> Kirim UDP"""
        cap = cv2.VideoCapture(cam_idx, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        
        # Set resolusi rendah (320x240) agar bandwidth LAN tidak mampet dan FPS tinggi
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

        if not cap.isOpened():
            print(f"[VISION-ENGINE] ERROR: Gagal membuka kamera pada indeks {cam_idx}")
            return

        # Jangkar waktu internal masing-masing thread (Lokal variabel, aman tidak bentrok)
        last_qr_check = 0.0
        cam_label = "FRONT" if is_front_cam else "BOTTOM"
        prefix = "front" if is_front_cam else "bottom"

        while self.is_running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            # --- PROSES MEMBACA QR CODE (Aktif di Kedua Kamera per 0.5 Detik) ---
            current_time = time.time()
            if current_time - last_qr_check > 0.5:
                last_qr_check = current_time
                
                # Eksekuasi pembacaan matriks gambar QR
                data, bbox, _ = self.qr_detector.detectAndDecode(frame)
                if bbox is not None and len(data) > 0:
                    x, y, w, h = int(bbox[0][0][0]), int(bbox[0][0][1]), int(bbox[0][2][0] - bbox[0][0][0]), int(bbox[0][2][1] - bbox[0][0][1])
                    
                    # Kunci data ke memori bersama khusus kubu masing-masing
                    self.latest_data[f"{prefix}_detected"] = True
                    self.latest_data[f"{prefix}_bbox"] = [x + w//2, y + h//2, w, h]
                    self.latest_data[f"{prefix}_qr_data"] = data
                    
                    # LOG INSTAN DI TERMINAL: Biar bisa langsung dipantau saat tes!
                    print(f"[{cam_label}-QR INTERCEPT] Terdeteksi String: '{data}' | Bbox Center: [{x + w//2}, {y + h//2}]")
                else:
                    self.latest_data[f"{prefix}_detected"] = False

            # --- KOMPRESI GAMBAR & KIRIM VIA UDP ---
            ret_encode, encoded_img = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 30])
            if ret_encode:
                bytes_data = encoded_img.tobytes()
                if len(bytes_data) < 61000:
                    try:
                        self.sock.sendto(bytes_data, destination_addr)
                    except Exception:
                        pass

            time.sleep(0.03)  # Batasi FPS streaming di kisaran ~30 FPS

        cap.release()

    def start_cameras(self):
        """Menyalakan pipa streaming kedua kamera secara paralel di latar belakang"""
        self.is_running = True
        print("[VISION-ENGINE] Pipa pengaliran data & Dual QR Scanner resmi berjalan aktif.")

        self.thread_front = threading.Thread(target=self._stream_logic, args=(self.cam_front_idx, self.addr_front, True))
        self.thread_bottom = threading.Thread(target=self._stream_logic, args=(self.cam_bottom_idx, self.addr_bottom, False))

        self.thread_front.daemon = True
        self.thread_bottom.daemon = True

        self.thread_front.start()
        self.thread_bottom.start()

    def get_latest_vision(self):
        """Dipanggil oleh main_ship.py untuk membaca status target otonom"""
        combined_data = self.latest_data.copy()
        
        # --- JEMBATAN BACKWARD COMPATIBILITY (Mencegah KeyError di main_ship.py) ---
        # Prioritaskan kamera bawah terlebih dahulu jika sedang dalam fase DESCENT/Menyelam
        if combined_data["bottom_detected"]:
            combined_data["target_detected"] = True
            combined_data["bbox"] = combined_data["bottom_bbox"]
            combined_data["qr_data"] = combined_data["bottom_qr_data"]
            
        elif combined_data["front_detected"]:
            combined_data["target_detected"] = True
            combined_data["bbox"] = combined_data["front_bbox"]
            combined_data["qr_data"] = combined_data["front_qr_data"]
            
        else:
            # Jika kedua kamera tidak melihat apa-apa
            combined_data["target_detected"] = False
            combined_data["bbox"] = [0, 0, 0, 0]
            combined_data["qr_data"] = ""
            
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
