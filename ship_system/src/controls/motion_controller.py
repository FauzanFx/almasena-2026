from controls.pid_controller import MiniPID

def clamp(val, min_val=1100, max_val=1900):
    return max(min_val, min(max_val, int(val)))

class MotionController:
    # Masukkan angka maksimum absolut yang kamu dapatkan di sini (1705)
    def __init__(self, min_encoder_tick=0, max_encoder_tick=1705):
        self.min_encoder_tick = min_encoder_tick
        self.max_encoder_tick = max_encoder_tick

        self.pid_depth   = MiniPID(kp=80.0, ki=1.0,  kd=5.0,  output_limits=(-100, 100))
        self.pid_pitch   = MiniPID(kp=3.0,  ki=0.1,  kd=0.5,  output_limits=(-150, 150))
        self.pid_yaw     = MiniPID(kp=2.0,  ki=0.0,  kd=0.2,  output_limits=(-100, 100))

        self.target_encoder = None
        self.target_depth = 0.0
        self.target_heading = 0.0
        self.target_pitch = 0.0

        self.heading_hold_active = False
        self.prev_hold_pitch_toggle = False
        self.pitch_baseline = 0.0
        self.last_pitch_effort = 0.0

        # PENGAMAN EDGE-DETECTION UNTUK TOMBOL GCS
        self.prev_zero_cmd = False
        self.prev_max_cmd = False

        self.SURGE_MAX_OFFSET = 400 * 0.3
        self.PITCH_MAX_OFFSET = 300 * 0.4
        self.YAW_MAX_OFFSET   = 300 * 0.3

    def process_and_send(self, cmds: dict, sensor_data: dict, attitude_data: dict,
                         software_kill_active: bool, stm32, pixhawk, logger) -> dict:

        encoder_ticks = sensor_data.get("encoder_ticks", 0)

        # Paksa reset ke 0 dan set target awal ke 0 pada boot pertama kali
        if self.target_encoder is None:
            self.target_encoder = 0.0
            stm32.send_zeroing()
            print("[MOTION] === BOOT: ENCODER & TARGET DI-RESET KE 0 ===")

        # --- BACA INPUT DARI GCS (TERMASUK YANG DI-BYPASS DARI MAIN_SHIP) ---
        zero_encoder_cmd = cmds.get("zero_encoder", False)
        max_encoder_cmd = cmds.get("max_encoder", False)

        # 1. PENANGKAP TOMBOL ZEROING (Tahan R3) DENGAN EDGE DETECTION
        if zero_encoder_cmd and not self.prev_zero_cmd:
            stm32.send_zeroing()
            self.min_encoder_tick = 0
            self.target_encoder = 0.0
            encoder_ticks = 0
            print("[MOTION] === BALLAST ZEROING (TITIK 0) DIAKTIFKAN VIA GCS! ===")
        self.prev_zero_cmd = zero_encoder_cmd

        # 2. PENANGKAP TOMBOL MAX LIMIT (Tahan L3) DENGAN EDGE DETECTION
        if max_encoder_cmd and not self.prev_max_cmd:
            if encoder_ticks > 500:
                self.max_encoder_tick = encoder_ticks
                if self.target_encoder > self.max_encoder_tick:
                    self.target_encoder = float(self.max_encoder_tick)
                print(f"[MOTION] === BALLAST MAX LIMIT DIKUNCI DI: {self.max_encoder_tick} ===")
            else:
                print("[MOTION] WARNING: Nilai max terlalu rendah, tarik lebih jauh dulu!")
        self.prev_max_cmd = max_encoder_cmd
        # ---------------------------------------------------------------------

        encoder_range = self.max_encoder_tick - self.min_encoder_tick
        if encoder_range <= 0: encoder_range = 1

        ballast_pct = int(max(0, min(100, ((encoder_ticks - self.min_encoder_tick) / encoder_range) * 100)))

        if software_kill_active:
            pixhawk.emergency_disarm_stop()
            stm32.send_manual_speed(0)
            stm32.send_target_position(target_pos=encoder_ticks, gripper_state=0)
            return {
                "ballast_pct": ballast_pct, "ballast_status": "KILL",
                "depth_hold": False, "heading_hold": False, "pitch_hold": False
            }

        current_depth = attitude_data.get("depth_raw", 0.0)
        current_pitch = attitude_data.get("pitch", 0.0)
        current_heading = attitude_data.get("heading", 0.0)

        ballast_cmd = cmds.get("ballast_cmd", cmds.get("ballast", 0))
        gripper_cmd = cmds.get("gripper_cmd", cmds.get("grip", 0))
        hold_pitch_toggle = cmds.get("hold_pitch", False)
        target_depth_auto = cmds.get("target_depth", None)

        if cmds.get("is_autonomous", False) and target_depth_auto is not None:
            virtual_joystick = self.pid_depth.compute(target_depth_auto, current_depth)
            self.target_encoder += (virtual_joystick * 2.5)
            self.target_encoder = max(self.min_encoder_tick, min(self.max_encoder_tick, self.target_encoder))
            stm32.send_target_position(int(self.target_encoder), gripper_cmd)
        else:
            if abs(ballast_cmd) > 15:
                if ballast_cmd > 0:
                    step_speed = 15.0 + (ballast_cmd * 0.2)
                else:
                    step_speed = -15.0 + (ballast_cmd * 0.2)

                self.target_encoder += step_speed
                self.target_encoder = max(self.min_encoder_tick, min(self.max_encoder_tick, self.target_encoder))

            stm32.send_target_position(int(self.target_encoder), gripper_cmd)

        ballast_speed = sensor_data.get("ballast_speed", 0)
        if ballast_speed > 5 or ballast_cmd > 5:
            ballast_status_str = "MENGISI"
        elif ballast_speed < -5 or ballast_cmd < -5:
            ballast_status_str = "MEMBUANG"
        else:
            ballast_status_str = "IDLE"

        raw_p = float(cmds.get("pitch", 0))
        if hold_pitch_toggle:
            if not self.prev_hold_pitch_toggle:
                self.target_pitch = current_pitch
                self.pitch_baseline = self.last_pitch_effort
                self.pid_pitch.reset()
            pitch_axis = self.pitch_baseline + self.pid_pitch.compute(self.target_pitch, current_pitch)
        else:
            if abs(raw_p) > 50: pitch_axis = (raw_p / 1000.0) * self.PITCH_MAX_OFFSET
            else: pitch_axis = self.pid_pitch.compute(0.0, current_pitch)
            self.last_pitch_effort = pitch_axis
        self.prev_hold_pitch_toggle = hold_pitch_toggle

        raw_y = float(cmds.get("yaw", 0))
        if abs(raw_y) > 50:
            self.heading_hold_active = False
            yaw_axis = (raw_y / 1000.0) * self.YAW_MAX_OFFSET
        else:
            if not self.heading_hold_active:
                self.target_heading = current_heading
                self.heading_hold_active = True
                self.pid_yaw.reset()
            yaw_axis = self.pid_yaw.compute(self.target_heading, current_heading)

        surge_axis = (float(cmds.get("surge", 0)) / 1000.0) * self.SURGE_MAX_OFFSET

        pixhawk.send_movement_target(
            pitch=1500, roll=1500, heave=clamp(1500 + pitch_axis),
            yaw=clamp(1500 + yaw_axis), surge=clamp(1500 + surge_axis)
        )

        return {
            "ballast_pct": ballast_pct,
            "ballast_status": ballast_status_str,
            "depth_hold": False,
            "heading_hold": self.heading_hold_active,
            "pitch_hold": hold_pitch_toggle
        }
