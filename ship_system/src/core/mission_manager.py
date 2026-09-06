# almasena-dev/ship_system/src/core/mission_manager.py

class MissionManager:
    def __init__(self):
        self.is_autonomous = False
        self.prev_autonomous = False
        self.auto_phase = "MANUAL"

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

        if self.is_autonomous and not self.prev_autonomous:
            self.auto_phase = "DESCENT"
            logger.push("Mode Otonom Dipicu: DESCENT", "sys")

        self.prev_autonomous = self.is_autonomous

        if not self.is_autonomous:
            self.auto_phase = "MANUAL"

            # --- MAPPING NORMAL: TIDAK DITUKAR ---
            cmds["surge"] = gcs_commands.get("surge", 0)
            cmds["yaw"] = gcs_commands.get("yaw", 0)
            cmds["pitch"] = gcs_commands.get("pitch", 0)
            
            # --- FIX: AMAN DARI PERBEDAAN NAMA KEY GCS ---
            cmds["ballast_cmd"] = gcs_commands.get("ballast_cmd", gcs_commands.get("ballast", 0))
            cmds["gripper_cmd"] = gcs_commands.get("gripper_cmd", gcs_commands.get("grip", gcs_commands.get("Grip", 0)))

        else:
            if vision_data.get("target_detected", False):
                x_center, y_center, _, _ = vision_data["bbox"]
                err_x = x_center - 320

                # --- FIX HARDWARE: TUKAR SURGE & YAW (Mode Otonom) ---
                cmds["surge"] = int(err_x * 1.5)  # Awalnya yaw
                cmds["yaw"] = 500                 # Awalnya surge
                # -----------------------------------------------------

                cmds["ballast_cmd"] = 0
                cmds["target_depth"] = None
                self.auto_phase = "TRACKING"
            else:
                if self.auto_phase == "DESCENT":
                    if current_depth >= 2.5:
                        self.auto_phase = "ASCENT"
                        logger.push("Otonom Phase: ASCENT", "sys")
                        cmds["target_depth"] = 0.2
                    else:
                        cmds["target_depth"] = 2.5

                elif self.auto_phase == "ASCENT":
                    if current_depth <= 0.2:
                        self.auto_phase = "DESCENT"
                        logger.push("Otonom Phase: DESCENT", "sys")
                        cmds["target_depth"] = 2.5
                    else:
                        cmds["target_depth"] = 0.2

        cmds["auto_phase"] = self.auto_phase
        return cmds
