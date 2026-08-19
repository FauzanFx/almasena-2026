# almasena-dev/ship_system/src/controls/pid_controller.py

import time

class MiniPID:
    """Modul Controller PID Sederhana dengan Clamping Anti-Windup"""
    def __init__(self, kp, ki, kd, output_limits=(-300, 300)):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.min_out, self.max_out = output_limits
        
        self.prev_error = 0.0
        self.integral = 0.0
        self.last_time = time.time()

    def compute(self, setpoint, measurement):
        now = time.time()
        dt = now - self.last_time
        if dt <= 0:
            dt = 0.05

        error = setpoint - measurement
        
        # Proportional
        p_term = self.kp * error
        
        # Integral dengan Clamping Anti-Windup
        self.integral += error * dt
        i_term = self.ki * self.integral
        i_term = max(self.min_out, min(self.max_out, i_term))
        
        # Derivative
        derivative = (error - self.prev_error) / dt
        d_term = self.kd * derivative

        # Limit Output Akhir
        output = p_term + i_term + d_term
        output = max(self.min_out, min(self.max_out, output))
        
        self.prev_error = error
        self.last_time = now
        return output

    def reset(self):
        self.prev_error = 0.0
        self.integral = 0.0
        self.last_time = time.time()
