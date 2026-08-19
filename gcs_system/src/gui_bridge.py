# almasena-dev/gcs_system/src/gui_bridge.py

import os
import asyncio
import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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
        gcs_root = os.path.dirname(current_dir)

        self.app.mount("/css", StaticFiles(directory=os.path.join(gcs_root, "css")), name="css")
        self.app.mount("/js", StaticFiles(directory=os.path.join(gcs_root, "js")), name="js")

        # Fallback Gambar Hitam NO SIGNAL
        blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(blank_frame, "NO SIGNAL", (230, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        _, blank_jpeg = cv2.imencode('.jpg', blank_frame)
        self.blank_bytes = b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + blank_jpeg.tobytes() + b'\r\n'

        @self.app.get("/")
        async def get_index():
            return FileResponse(os.path.join(gcs_root, "GUI.html"))

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
        # --- STREAM KAMERA DEPAN ---
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

        # --- STREAM KAMERA BAWAH ---
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

    def set_video_engine(self, video_engine):
        self.video_engine = video_engine

    def set_control_callback(self, callback):
        self.control_callback = callback

    def broadcast_telemetry(self, telemetry_data: dict):
        for ws in list(self.active_telemetry_sockets):
            try:
                asyncio.run_coroutine_threadsafe(ws.send_json(telemetry_data), self.loop)
            except Exception:
                pass

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        config = uvicorn.Config(app=self.app, host=self.host, port=self.port, log_level="error")
        server = uvicorn.Server(config)
        self.loop.run_until_complete(server.serve())

    def start_in_thread(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()
