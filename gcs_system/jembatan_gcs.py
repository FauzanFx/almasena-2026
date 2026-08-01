import asyncio
import json
import random
import time
import cv2
import sys
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from src.cv_processor import CVProcessor

cv_engine = CVProcessor()


sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

# 1. IMPORT MODUL BACKEND BUATAN TEMANMU
from net_handler import NetHandler
from video_receiver import VideoReceiver

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Mengizinkan akses dari port berapapun (termasuk 5500)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. INISIALISASI SUBSISTEM ROV
net_manager = NetHandler(rov_ip="127.0.0.1", send_port=5005, recv_port=5006)

video_engine = VideoReceiver(port_front=5000, port_bottom=5001)
video_engine.start()

current_commands = {
    "surge": 0, "yaw": 0, "heave": 0, "pitch": 0,
    "ballast_cmd": 0, "gripper_cmd": 0,
    "autonomous_mode": False, "kill_switch": False
}

# ==========================================
# JALUR 1: VIDEO (HTTP MJPEG STREAMING)
# ==========================================
def generate_mjpeg(camera_key):
    while True:
        frame_front, frame_bottom = video_engine.get_latest_frames()
        frame = frame_front if camera_key == "front" else frame_bottom

        if frame is not None:
            # 1. Masukkan ke modul CV
            processed_frame = cv_engine.process_frame(frame)
            
            # 2. Failsafe: Pastikan frame hasil proses tidak kosong sebelum di-encode
            if processed_frame is not None:
                ret, buffer = cv2.imencode('.jpg', processed_frame)
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

        time.sleep(0.03)

@app.get("/video/depan")
async def video_depan():
    return StreamingResponse(generate_mjpeg("front"), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/video/bawah")
async def video_bawah():
    return StreamingResponse(generate_mjpeg("bottom"), media_type="multipart/x-mixed-replace; boundary=frame")

# ==========================================
# JALUR 2: TELEMETRI (WEBSOCKET)
# ==========================================
@app.websocket("/ws/telemetry")
async def telemetry_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("[GCS-WEB] Klien Web Telemetri Terhubung.")
    try:
        while True:
            loop_start = time.perf_counter()

            raw_telemetry = net_manager.receive_telemetry_from_rov()

            # ── Nilai default (dipakai jika sensor terkait belum tersedia di paket telemetri) ──
            depth = 0.0
            batt_pct = 0.0
            heading = 0.0
            roll = 0.0
            pitch = 0.0
            temp = 25.0

            if raw_telemetry:
                # Beberapa firmware mengirim data di dalam sub-dict "sensors",
                # yang lain mengirim langsung di root dict. Dukung keduanya.
                ship_data = raw_telemetry.get('sensors', raw_telemetry)

                depth = ship_data.get('depth_raw', depth)
                batt_pct = ship_data.get('voltage_raw', batt_pct)
                heading = ship_data.get('heading_raw', heading)
                roll = ship_data.get('roll_raw', roll)
                pitch = ship_data.get('pitch_raw', pitch)
                temp = ship_data.get('temp_raw', temp)

            # ── Ping: waktu bolak-balik permintaan telemetri ke ROV (ms) ──
            # TODO: ganti dengan pengukuran RTT asli dari net_manager jika sudah tersedia.
            ping_ms = round((time.perf_counter() - loop_start) * 1000)
            if ping_ms <= 0:
                ping_ms = random.randint(30, 60)  # nilai dummy sementara

            gui_data = {
                "depth": round(depth, 2),
                "heading": round(heading, 1) % 360,
                "roll": round(roll, 1),
                "pitch": round(pitch, 1),
                "ping": ping_ms,
                "batt_pct": round(batt_pct, 1),
                "temp": round(temp, 1),
            }

            await websocket.send_json(gui_data)
            await asyncio.sleep(0.05)

    except WebSocketDisconnect:
        print("[GCS-WEB] Klien Web Telemetri Terputus")

# ==========================================
# JALUR 3: KENDALI / KONTROL (WEBSOCKET)
# ==========================================
@app.websocket("/ws/control")
async def control_endpoint(websocket: WebSocket):
    await websocket.accept()
    global current_commands
    print("[GCS-WEB] Klien Web Kontrol Terhubung.")
    try:
        while True:
            data = await websocket.receive_text()
            gui_cmd = json.loads(data)

            current_commands["surge"] = 0
            current_commands["yaw"] = 0
            current_commands["heave"] = 0

            if gui_cmd.get("gerak") == "Maju":
                current_commands["surge"] = 1000
            elif gui_cmd.get("gerak") == "Mundur":
                current_commands["surge"] = -1000
            elif gui_cmd.get("gerak") == "Kanan":
                current_commands["yaw"] = 1000
            elif gui_cmd.get("gerak") == "Kiri":
                current_commands["yaw"] = -1000

            net_manager.send_commands_to_rov(current_commands)

    except WebSocketDisconnect:
        print("[GCS-WEB] Klien Web Kontrol Terputus. Menghentikan ROV (Failsafe Mode).")
        current_commands = {k: 0 if isinstance(v, int) else False for k, v in current_commands.items()}
        net_manager.send_commands_to_rov(current_commands)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)