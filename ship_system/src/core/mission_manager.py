# almasena-dev/ship_system/src/core/mission_manager.py

import time

class MissionManager:
    def __init__(self):
        self.is_autonomous = False
        self.prev_autonomous = False
        self.auto_phase = "MANUAL"
        
        # Timer untuk state machine otonom
        self.phase_start_time = 0.0

    def update(self, gcs_commands: dict, vision_data: dict, current_depth: float, software_kill_active: bool, logger) -> dict:
        cmds = {
            "surge": 0,
            "yaw": 0,
            "pitch": 0,
            "ballast_cmd": 0,
            "gripper_cmd": 0,
            "hold_pitch": False,
            "is_autonomous": False,
            "auto_phase": "MANUAL",
            "target_depth": None
        }

        if software_kill_active:
            self.is_autonomous = False
            self.auto_phase = "MANUAL"
            return cmds

        if not gcs_commands:
            return cmds

        self.is_autonomous = gcs_commands.get("autonomous_mode", False)
        cmds["hold_pitch"] = gcs_commands.get("hold_pitch", False)
        cmds["is_autonomous"] = self.is_autonomous

        # --- DETEKSI TOMBOL AUTONOMOUS BARU DITEKAN ---
        if self.is_autonomous and not self.prev_autonomous:
            self.auto_phase = "AUTO_MUNDUR"
            self.phase_start_time = time.time()
            if logger:
                logger.push("[AUTO] Sequence Dimulai: Phase 1 (Mundur)", "sys")

        self.prev_autonomous = self.is_autonomous

        # --- MODE MANUAL ---
        if not self.is_autonomous:
            self.auto_phase = "MANUAL"
            cmds["surge"] = gcs_commands.get("surge", 0)
            cmds["yaw"] = gcs_commands.get("yaw", 0)
            cmds["pitch"] = gcs_commands.get("pitch", 0)
            cmds["ballast_cmd"] = gcs_commands.get("ballast_cmd", gcs_commands.get("ballast", 0))
            cmds["gripper_cmd"] = gcs_commands.get("gripper_cmd", gcs_commands.get("grip", gcs_commands.get("Grip", 0)))
            cmds["auto_phase"] = self.auto_phase
            return cmds

        # --- MODE AUTONOMOUS (TIME-BASED STATE MACHINE) ---
        now = time.time()
        elapsed = now - self.phase_start_time

        if self.auto_phase == "AUTO_MUNDUR":
            if elapsed < 1.0:
                cmds["surge"] = -500  # Mundur 50% power
                cmds["ballast_cmd"] = 0
            else:
                self.auto_phase = "AUTO_TARIK_BALLAST"
                self.phase_start_time = now
                if logger:
                    logger.push("[AUTO] Phase 2: Tarik Ballast 3 Detik", "sys")

        elif self.auto_phase == "AUTO_TARIK_BALLAST":
            if elapsed < 3.0:
                cmds["surge"] = 0
                cmds["ballast_cmd"] = -100  # Tarik full (STM32 pwm_speed negatif)
            else:
                self.auto_phase = "AUTO_MAJU"
                self.phase_start_time = now
                if logger:
                    logger.push("[AUTO] Phase 3: Maju 1 Detik", "sys")

        elif self.auto_phase == "AUTO_MAJU":
            if elapsed < 1.0:
                cmds["surge"] = 500  # Maju 50% power
                cmds["ballast_cmd"] = 0
            else:
                self.auto_phase = "AUTO_DORONG_BALLAST"
                self.phase_start_time = now
                if logger:
                    logger.push("[AUTO] Phase 4: Dorong Ballast 3 Detik", "sys")

        elif self.auto_phase == "AUTO_DORONG_BALLAST":
            if elapsed < 3.0:
                cmds["surge"] = 0
                cmds["ballast_cmd"] = 100  # Dorong full (STM32 pwm_speed positif)
            else:
                self.auto_phase = "AUTO_SELESAI"
                if logger:
                    logger.push("[AUTO] Sequence Selesai. Menunggu Manual Override.", "sys")

        elif self.auto_phase == "AUTO_SELESAI":
            # Berhenti total
            cmds["surge"] = 0
            cmds["yaw"] = 0
            cmds["pitch"] = 0
            cmds["ballast_cmd"] = 0

        cmds["auto_phase"] = self.auto_phase
        return cmds