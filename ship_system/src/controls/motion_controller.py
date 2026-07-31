# almasena-dev/ship_system/src/controls/motion_controller.py

from controls.pid_controller import MiniPID

def clamp(val, min_val=1100, max_val=1900):
    return max(min_val, min(max_val, int(val)))

class MotionController:
    def __init__(self, max_encoder_tick=10000.0):
        self.max_encoder_tick = max_encoder_tick

        # KEDUA PID KEMBALI KE RASPI
        self.pid_depth   = MiniPID(kp=80.0, ki=1.0,   kd=5.0,  output_limits=(-100, 100))
        self.pid_ballast = MiniPID(kp=0.1, ki=0.0, kd=0.0, output_limits=(-100, 100))
        self.pid_pitch   = MiniPID(kp=3.0,  ki=0.1,   kd=0.5,  output_limits=(-150, 150))
        self.pid_yaw     = MiniPID(kp=2.0,  ki=0.0,   kd=0.2,  output_limits=(-100, 100))

        self.target_encoder = 5000.0 
        self.target_depth = 0.0
        self.target_heading = 0.0
        self.target_pitch = 0.0

        self.volume_hold_active = True
        self.heading_hold_active = False
        self.prev_hold_pitch_toggle = False

        self.pitch_baseline = 0.0
        self.last_pitch_effort = 0.0

        self.SURGE_MAX_OFFSET = 400 * 0.5
        self.PITCH_MAX_OFFSET = 300 * 0.5
        self.YAW_MAX_OFFSET   = 300 * 0.5

    def process_and_send(self, cmds: dict, sensor_data: dict, attitude_data: dict,
                         software_kill_active: bool, stm32, pixhawk, logger) -> dict:
        
        encoder_ticks = sensor_data.get("encoder_ticks", 0)
        ballast_pct = int(max(0, min(100, (encoder_ticks / self.max_encoder_tick) * 100)))

        if software_kill_active:
            pixhawk.emergency_disarm_stop()
            # Kirim 0 kecepatan motor dan matikan gripper
            stm32.send_raw_control(ballast_speed=0, gripper_state=0)
            return {
                "ballast_pct": ballast_pct,
                "ballast_status": "KILL",
                "depth_hold": False,
                "heading_hold": False,
                "pitch_hold": False
            }

        current_depth = attitude_data.get("depth_raw", 0.0)
        current_pitch = attitude_data.get("pitch", 0.0)
        current_heading = attitude_data.get("heading", 0.0)

        ballast_cmd = cmds.get("ballast_cmd", 0)
        gripper_cmd = cmds.get("gripper_cmd", 0)
        hold_pitch_toggle = cmds.get("hold_pitch", False)
        target_depth_auto = cmds.get("target_depth", None)

        # 1. OUTER LOOP
        if cmds.get("is_autonomous", False) and target_depth_auto is not None:
            virtual_joystick = self.pid_depth.compute(target_depth_auto, current_depth)
            self.target_encoder += (virtual_joystick * 2.5)
            self.volume_hold_active = False
        elif abs(ballast_cmd) > 5:
            self.target_encoder += (ballast_cmd * 8) 
            self.volume_hold_active = False
            self.pid_depth.reset()
        else:
            self.volume_hold_active = True
            self.pid_depth.reset() 

        self.target_encoder = max(0, min(self.max_encoder_tick, self.target_encoder))

        # 2. INNER LOOP
        ballast_speed_stm32 = int(max(-100, min(100, self.pid_ballast.compute(self.target_encoder, encoder_ticks))))

        if ballast_speed_stm32 > 5:
            ballast_status_str = "MENGISI"
        elif ballast_speed_stm32 < -5:
            ballast_status_str = "MEMBUANG"
        else:
            ballast_status_str = "IDLE"

        # PITCH KONTROL
        raw_p = float(cmds.get("pitch", 0))
        if hold_pitch_toggle:
            if not self.prev_hold_pitch_toggle:
                self.target_pitch = current_pitch
                self.pitch_baseline = self.last_pitch_effort
                self.pid_pitch.reset()
                logger.push(f"Pitch Hold AKTIF: {self.target_pitch:.1f}° | Base PWM: {self.pitch_baseline:.1f}", "sys")

            pid_correction = self.pid_pitch.compute(self.target_pitch, current_pitch)
            pitch_axis = self.pitch_baseline + pid_correction
        else:
            if abs(raw_p) > 50:
                pitch_axis = (raw_p / 1000.0) * self.PITCH_MAX_OFFSET
            else:
                pitch_axis = self.pid_pitch.compute(0.0, current_pitch)
            self.last_pitch_effort = pitch_axis

        self.prev_hold_pitch_toggle = hold_pitch_toggle

        # YAW & SURGE KONTROL
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

        cmd_heave = clamp(1500 + pitch_axis)
        cmd_yaw   = clamp(1500 + yaw_axis)
        cmd_surge = clamp(1500 + surge_axis)

        pixhawk.send_movement_target(
            pitch=1500, roll=1500, heave=cmd_heave, yaw=cmd_yaw, surge=cmd_surge
        )
        
        # 3. KIRIM RAW PWM SPEED KE STM32
        stm32.send_raw_control(ballast_speed=ballast_speed_stm32, gripper_state=gripper_cmd)

        return {
            "ballast_pct": ballast_pct,
            "ballast_status": ballast_status_str,
            "depth_hold": self.volume_hold_active,
            "heading_hold": self.heading_hold_active,
            "pitch_hold": hold_pitch_toggle
        }
