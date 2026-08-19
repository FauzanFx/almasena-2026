# almasena-dev/ship_system/src/utils/ship_logger.py

import time

class ShipLogger:
    def __init__(self, max_logs=15):
        self.max_logs = max_logs
        self.logs = []

    def push(self, msg: str, log_type: str = "info"):
        """Menambahkan log baru dengan timestamp riil."""
        timestamp = time.strftime("%H:%M:%S")
        self.logs.append({"ts": timestamp, "msg": msg, "type": log_type})
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)

    def get_logs(self):
        return self.logs
