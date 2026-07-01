# almasena-dev/ship_system/src/vision/vision_processor.py

import cv2
import threading
import time
import os
from pathlib import Path
from ultralytics import YOLO

class VisionProcessor:
    def __init__(self, model_path="models/yolov8n.pt", gcs_ip="192.168.1.10", port_front=5000, port_bottom=5001):
        self.model_path = model_path
        self.gcs_ip = gcs_ip
        self.port_front = port_front
        self.port_bottom = port_bottom
        
        self.is_running = False
        self.model = None
        
        # State interface penampung data tracking otonom untuk main_ship.py
        self.latest_vision_data = {
            "target_detected": False,
            "bbox": []  # Format koordinat: [x_center, y_center, width, height]
        }
        
        # Pipeline GStreamer memanfaatkan hardware acceleration Raspberry Pi 4 (v4l2h264enc)
        # Menembak video H.264 stream ke IP Laptop Darat secara real-time via UDP
        self.gst_out_front = (
            f"v4l2src device=/dev/video0 ! video/x-raw, width=640, height=480, framerate=30/1 ! "
            f"videoconvert ! v4l2h264enc ! rtph264pay config-interval=1 pt=96 ! "
            f"udpsink host={self.gcs_ip} port={self.port_front} sync=false"
        )
        
        self.gst_out_bottom = (
            f"v4l2src device=/dev/video2 ! video/x-raw, width=640, height=480, framerate=30/1 ! "
            f"videoconvert ! v4l2h264enc ! rtph264pay config-interval=1 pt=96 ! "
            f"udpsink host={self.gcs_ip} port={self.port_bottom} sync=false"
        )

    def init_model(self):
        """Memuat bobot model YOLOv8 secara dinamis menggunakan Absolute Path"""
        try:
            # Deteksi lokasi absolut file ini (~/ship_system/src/vision/)
            current_file_path = Path(__file__).resolve()
            
            # Mundur 2 tingkat ke induk utama (folder 'ship_system')
            ship_system_root = current_file_path.parents[2]
            
            # Satukan secara kokoh dengan relative path dari config YAML
            absolute_model_path = os.path.join(ship_system_root, self.model_path)
            
            print(f"[VISION-YOLO] Memuat arsitektur model dari path absolut: {absolute_model_path}")
            self.model = YOLO(absolute_model_path)
            print("[VISION-YOLO] Sukses mengunci model YOLOv8 Headless Engine.")
            return True
        except Exception as e:
            print(f"[VISION-YOLO] ERROR: Gagal inisialisasi bobot model: {e}")
            return False

    def start_cameras(self):
        """Memicu eksekusi thread latar belakang untuk ke-2 kamera secara paralel"""
        self.is_running = True
        
        # Thread Kamera Depan (Misi Navigasi Gerbang Lintasan)
        self.front_thread = threading.Thread(target=self._front_camera_loop, daemon=True)
        self.front_thread.start()
        
        # Thread Kamera Bawah (Misi Tracking Payload & Scan QR Code)
        self.bottom_thread = threading.Thread(target=self._bottom_camera_loop, daemon=True)
        self.bottom_thread.start()
        
        print("[VISION-ENGINE] Pipa pengaliran data 2 unit kamera resmi berjalan aktif.")

    def _front_camera_loop(self):
        """Loop independen kamera depan untuk visualisasi live-feed darat"""
        cap_front = cv2.VideoCapture(0)  # Mengikat /dev/video0 (Kamera Depan)
        out_front = cv2.VideoWriter(self.gst_out_front, cv2.CAP_GSTREAMER, 0, 30.0, (640, 480))
        
        while self.is_running and cap_front.isOpened():
            ret, frame = cap_front.read()
            if not ret:
                continue
            
            # Kirim frame mentah langsung menembus port 5000 jaringan LAN
            out_front.write(frame)
            
        cap_front.release()
        print("[VISION-ENGINE] Saluran Kamera Depan Resmi Dihentikan.")

    def _bottom_camera_loop(self):
        """Loop independen kamera bawah: AI Inference YOLOv8 + Stream Jaringan LAN"""
        cap_bottom = cv2.VideoCapture(2)  # Mengikat /dev/video2 (Kamera Bawah)
        out_bottom = cv2.VideoWriter(self.gst_out_bottom, cv2.CAP_GSTREAMER, 0, 30.0, (640, 480))
        
        while self.is_running and cap_bottom.isOpened():
            ret, frame = cap_bottom.read()
            if not ret:
                continue
                
            # Jalankan deteksi objek otonom jika engine YOLO terinisialisasi
            if self.model:
                # Batasi ukuran citra ke imgsz=320 untuk menjaga kestabilan FPS komputasi Pi 4
                results = self.model(frame, imgsz=320, verbose=False)[0]
                
                object_found = False
                for box in results.boxes:
                    # Ambil bounding box objek kustom pertama yang berhasil ditangkap di kolam
                    xywh = box.xywh[0].tolist()
                    
                    self.latest_vision_data["target_detected"] = True
                    self.latest_vision_data["bbox"] = [round(coord, 2) for coord in xywh]
                    object_found = True
                    break  # Kunci target utama terlebih dahulu
                    
                if not object_found:
                    self.latest_vision_data["target_detected"] = False
                    self.latest_vision_data["bbox"] = []
            
            # Kirim frame kamera bawah sekaligus menembus port 5001 jaringan LAN
            out_bottom.write(frame)
            
        cap_bottom.release()
        print("[VISION-ENGINE] Saluran Kamera Bawah Resmi Dihentikan.")

    def get_latest_vision(self):
        """Menyediakan data koordinat target otonom aktual untuk diserap oleh main_ship.py"""
        return self.latest_vision_data

    def stop(self):
        """Mematikan seluruh thread pemrosesan gambar secara aman saat shutdown"""
        self.is_running = False
        print("[VISION-ENGINE] Seluruh pipa pemrosesan gambar ditutup secara bersih.")
