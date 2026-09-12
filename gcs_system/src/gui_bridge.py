#almasena-dev/gcs_system/src/gui_bridge.py

import os
import time
import json
import asyncio
import cv2
import numpy as np
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
import uvicorn
import threading


class GUIBridge:
    def __init__(self, host="0.0.0.0", port=8000):
        self.host = host
        self.port = port
        self.app = FastAPI()
        self.active_telemetry_sockets = []
        self.control_callback = None
        self.video_engine = None

        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.gcs_root = os.path.dirname(current_dir)
        self.recordings_dir = os.path.join(self.gcs_root, "recordings")
        self.screenshots_dir = os.path.join(self.gcs_root, "screenshots")
        os.makedirs(self.recordings_dir, exist_ok=True)
        os.makedirs(self.screenshots_dir, exist_ok=True)

        self.app.mount("/css", StaticFiles(directory=os.path.join(self.gcs_root, "css")), name="css")
        self.app.mount("/js", StaticFiles(directory=os.path.join(self.gcs_root, "js")), name="js")

        # State Perekaman Hybrid
        self.auto_log_enabled = False
        self.is_recording = False
        self.current_session_name = None
        self.current_session_dir = None
        self.trajectory_file_handle = None
        self.session_start_time = 0.0
        self.session_waypoints_count = 0

        # Fallback Gambar Hitam NO SIGNAL
        blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(blank_frame, "NO SIGNAL", (230, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        _, blank_jpeg = cv2.imencode('.jpg', blank_frame)
        self.blank_bytes = b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + blank_jpeg.tobytes() + b'\r\n'

        self._setup_routes()

    def _setup_routes(self):
        @self.app.get("/")
        async def get_index():
            return FileResponse(os.path.join(self.gcs_root, "GUI.html"))

        @self.app.post("/api/command")
        async def post_command(cmd: dict):
            if self.control_callback:
                self.control_callback(cmd)
            return {"status": "ok"}

        @self.app.post("/api/hardware")
        async def post_hardware(cmd: dict):
            if self.control_callback:
                self.control_callback(cmd)
            return {"status": "ok"}

        # --- CONTROLLER SCREENSHOT & RECORDING TRIGGER ---
        @self.app.post("/api/screenshot")
        async def trigger_screenshot():
            if not self.video_engine:
                return {"status": "error", "msg": "Video engine not connected"}
            saved = self.video_engine.take_screenshot(self.screenshots_dir)
            return {"status": "ok", "saved_files": saved}

        @self.app.post("/api/record/toggle_autolog")
        async def toggle_autolog():
            self.auto_log_enabled = not self.auto_log_enabled
            if not self.auto_log_enabled and self.is_recording:
                self._stop_mission_recording()
            return {
                "status": "ok",
                "auto_log_enabled": self.auto_log_enabled,
                "is_recording": self.is_recording
            }

        @self.app.get("/api/record/status")
        async def get_record_status():
            return {
                "auto_log_enabled": self.auto_log_enabled,
                "is_recording": self.is_recording,
                "current_session": self.current_session_name
            }

        # --- STREAM VIDEO LIVE ---
        async def generate_front_stream():
            while True:
                frame_bytes = self.blank_bytes
                if self.video_engine:
                    frame_front, _ = self.video_engine.get_latest_frames()
                    if frame_front is not None:
                        ret, jpeg = cv2.imencode('.jpg', frame_front)
                        if ret:
                            frame_bytes = b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n'
                yield frame_bytes
                await asyncio.sleep(0.03)

        @self.app.get("/video/front")
        async def video_front_endpoint():
            return StreamingResponse(generate_front_stream(), media_type="multipart/x-mixed-replace; boundary=frame")

        async def generate_bottom_stream():
            while True:
                frame_bytes = self.blank_bytes
                if self.video_engine:
                    _, frame_bottom = self.video_engine.get_latest_frames()
                    if frame_bottom is not None:
                        ret, jpeg = cv2.imencode('.jpg', frame_bottom)
                        if ret:
                            frame_bytes = b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n'
                yield frame_bytes
                await asyncio.sleep(0.03)

        @self.app.get("/video/bottom")
        async def video_bottom_endpoint():
            return StreamingResponse(generate_bottom_stream(), media_type="multipart/x-mixed-replace; boundary=frame")

        # --- REPLAY API ---
        @self.app.get("/api/replay/sessions")
        async def list_replay_sessions():
            """Mengembalikan daftar sesi misi yang tersimpan di disk"""
            sessions = []
            if os.path.exists(self.recordings_dir):
                for d in sorted(os.listdir(self.recordings_dir), reverse=True):
                    full_path = os.path.join(self.recordings_dir, d)
                    if os.path.isdir(full_path):
                        meta_file = os.path.join(full_path, "meta.json")
                        meta_data = {}
                        if os.path.exists(meta_file):
                            try:
                                with open(meta_file, "r") as f:
                                    meta_data = json.load(f)
                            except Exception:
                                pass
                        sessions.append({
                            "session_id": d,
                            "has_video": os.path.exists(os.path.join(full_path, "front.mp4")),
                            "meta": meta_data
                        })
            return {"sessions": sessions}

        @self.app.get("/api/replay/session/{session_name}")
        async def get_replay_session_data(session_name: str):
            """Mengambil data lintasan lengkap suatu sesi untuk di-render di canvas"""
            session_path = os.path.join(self.recordings_dir, session_name)
            traj_file = os.path.join(session_path, "trajectory.jsonl")
            meta_file = os.path.join(session_path, "meta.json")

            if not os.path.exists(traj_file):
                return {"status": "error", "msg": "Session not found"}

            trajectory_points = []
            with open(traj_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            trajectory_points.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

            meta = {}
            if os.path.exists(meta_file):
                with open(meta_file, "r") as f:
                    meta = json.load(f)

            return {
                "status": "ok",
                "session_id": session_name,
                "meta": meta,
                "trajectory": trajectory_points
            }

        @self.app.get("/api/replay/frame")
        async def get_replay_frame(session: str = Query(...), cam: str = Query("front"), ms: float = Query(0.0)):
            """Menarik satu frame JPEG dari video MP4 sesuai milidetik yang diminta"""
            video_path = os.path.join(self.recordings_dir, session, f"{cam}.mp4")
            if not os.path.exists(video_path):
                return Response(status_code=404)

            cap = cv2.VideoCapture(video_path)
            cap.set(cv2.CAP_PROP_POS_MSEC, ms)
            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                return Response(status_code=404)

            ret_enc, jpeg = cv2.imencode('.jpg', frame)
            if not ret_enc:
                return Response(status_code=500)

            return Response(content=jpeg.tobytes(), media_type="image/jpeg")

        # --- WEBSOCKET TELEMETRY ---
        @self.app.websocket("/ws/telemetry")
        async def ws_telemetry_endpoint(websocket: WebSocket):
            await websocket.accept()
            self.active_telemetry_sockets.append(websocket)
            try:
                while True:
                    await asyncio.sleep(1)
            except WebSocketDisconnect:
                if websocket in self.active_telemetry_sockets:
                    self.active_telemetry_sockets.remove(websocket)

    def _start_mission_recording(self):
        """Membuat folder misi baru dan memulai sinkronisasi file"""
        self.session_start_time = time.time()
        self.current_session_name = f"RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.current_session_dir = os.path.join(self.recordings_dir, self.current_session_name)
        os.makedirs(self.current_session_dir, exist_ok=True)

        # 1. Buka file trajectory.jsonl
        traj_path = os.path.join(self.current_session_dir, "trajectory.jsonl")
        self.trajectory_file_handle = open(traj_path, "w", buffering=1)
        self.session_waypoints_count = 0

        # 2. Perintahkan VideoEngine memulai rekaman video MP4
        if self.video_engine:
            self.video_engine.start_recording(self.current_session_dir)

        self.is_recording = True
        print(f"[HYBRID-RECORDER] >>> Sesi Rekaman Misi Dimulai: {self.current_session_name}")

    def _stop_mission_recording(self):
        """Menutup file video dan menyimpan meta.json"""
        if not self.is_recording:
            return

        self.is_recording = False
        duration_sec = round(time.time() - self.session_start_time, 2)

        # 1. Hentikan VideoEngine
        if self.video_engine:
            self.video_engine.stop_recording()

        # 2. Tutup file trajectory
        if self.trajectory_file_handle and not self.trajectory_file_handle.closed:
            self.trajectory_file_handle.close()

        # 3. Tulis meta data ringkasan misi
        meta = {
            "session_id": self.current_session_name,
            "duration_sec": duration_sec,
            "total_waypoints": self.session_waypoints_count,
            "created_at": datetime.now().isoformat()
        }
        meta_path = os.path.join(self.current_session_dir, "meta.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        print(f"[HYBRID-RECORDER] <<< Sesi Rekaman Selesai ({duration_sec}s, {self.session_waypoints_count} pts)")
        self.current_session_name = None
        self.current_session_dir = None

    def broadcast_telemetry(self, telemetry_data: dict):
        """Mengevaluasi status arming untuk trigger hybrid serta mencatat titik jalur"""
        sensors = telemetry_data.get("sensors", {}) if isinstance(telemetry_data.get("sensors"), dict) else telemetry_data

        is_armed = bool(
            telemetry_data.get("is_armed") or 
            sensors.get("is_armed") or 
            False
        )

        pos_x = telemetry_data.get("pos_x") if "pos_x" in telemetry_data else sensors.get("pos_x", 0.0)
        pos_y = telemetry_data.get("pos_y") if "pos_y" in telemetry_data else sensors.get("pos_y", 0.0)
        depth_raw = telemetry_data.get("depth_raw") if "depth_raw" in telemetry_data else sensors.get("depth_raw", 0.0)
        heading = telemetry_data.get("heading") if "heading" in telemetry_data else sensors.get("heading", 0.0)

        # 3. Ratakan (flatten) ke telemetry_data agar browser (main.js) langsung menerima pos_x & is_armed
        telemetry_data["is_armed"] = is_armed
        telemetry_data["pos_x"] = pos_x
        telemetry_data["pos_y"] = pos_y
        telemetry_data["depth_raw"] = depth_raw
        telemetry_data["heading"] = heading

        # 4. Evaluasi Trigger Hybrid Perekaman
        should_record = self.auto_log_enabled and is_armed

        if should_record and not self.is_recording:
            self._start_mission_recording()
        elif not should_record and self.is_recording:
            self._stop_mission_recording()

        # 5. Catat ke file JSONL jika sesi rekaman sedang berjalan
        if self.is_recording and self.trajectory_file_handle:
            elapsed_ms = int((time.time() - self.session_start_time) * 1000)
            pt = {
                "elapsed_ms": elapsed_ms,
                "x": pos_x,
                "y": pos_y,
                "depth": depth_raw,
                "heading": heading,
                "armed": is_armed
            }
            self.trajectory_file_handle.write(json.dumps(pt) + "\n")
            self.session_waypoints_count += 1

        telemetry_data["is_recording_active"] = self.is_recording
        telemetry_data["auto_log_enabled"] = self.auto_log_enabled

        # 6. Broadcast data ke GUI via WebSocket
        for ws in list(self.active_telemetry_sockets):
            try:
                asyncio.run_coroutine_threadsafe(ws.send_json(telemetry_data), self.loop)
            except Exception:
                pass
    def set_video_engine(self, video_engine):
        self.video_engine = video_engine

    def set_control_callback(self, callback):
        self.control_callback = callback

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        config = uvicorn.Config(app=self.app, host=self.host, port=self.port, log_level="error")
        server = uvicorn.Server(config)
        self.loop.run_until_complete(server.serve())

    def start_in_thread(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()
