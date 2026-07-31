# almasena-dev/ship_system/src/core/failsafe.py

import time

class FailsafeManager:
    def __init__(self, timeout_threshold=1.0):
        self.timeout_threshold = timeout_threshold
        self.last_gcs_packet_time = time.time()
        self.software_kill_active = False

    def update(self, gcs_commands: dict, logger, pixhawk) -> bool:
        """
        Memeriksa status heartbeat GCS dan Kill Switch.
        Mengembalikan True jika status Kill Switch sedang aktif.
        """
        if gcs_commands:
            self.last_gcs_packet_time = time.time()
            kill_trigger = gcs_commands.get("kill_switch", False)

            if kill_trigger and not self.software_kill_active:
                self.software_kill_active = True
                logger.push("EMERGENCY: Kill Switch Dipicu!", "err")
                pixhawk.emergency_disarm_stop()  # <--- DISARM PIXHAWK SEKETIKA
            else:
                if self.software_kill_active and not kill_trigger:
                    logger.push("Kill Switch Released. Re-Arming Pixhawk...", "sys")
                    pixhawk.set_mode('MANUAL')
                    pixhawk.set_arm_state(arm=True)
                self.software_kill_active = kill_trigger
        else:
            if (time.time() - self.last_gcs_packet_time) > self.timeout_threshold:
                if not self.software_kill_active:
                    logger.push("FAILSAFE: UDP GCS Timeout! Memaksa Kill Switch...", "err")
                    self.software_kill_active = True
                    pixhawk.emergency_disarm_stop()  # <--- DISARM KARENA TIMEOUT

        return self.software_kill_active
