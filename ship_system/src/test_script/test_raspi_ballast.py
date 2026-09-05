import os
import sys
import time
import yaml
from pathlib import Path
import RPi.GPIO as GPIO

# Setup Path Modul
current_file = Path(__file__).resolve()
ship_system_root = current_file.parents[2]
sys.path.append(os.path.join(ship_system_root, "src"))

from network.net_bridge import NetBridge

# ================= KONFIGURASI PIN (BCM) =================
PWM_PIN = 18
IN1_PIN = 23
IN2_PIN = 24
ENCA_PIN = 20
ENCB_PIN = 21
# =========================================================

# Variabel Global Encoder
encoder_ticks = 0

def encoder_callback(channel):
    global encoder_ticks
    # Logika sederhana pembacaan Kuadratur Encoder
    if GPIO.input(ENCB_PIN) == GPIO.input(ENCA_PIN):
        encoder_ticks += 1
    else:
        encoder_ticks -= 1

def set_motor(pwm_obj, speed):
    if abs(speed) < 5:
        GPIO.output(IN1_PIN, GPIO.LOW)
        GPIO.output(IN2_PIN, GPIO.LOW)
        pwm_obj.ChangeDutyCycle(0)
        return

    # Set arah
    if speed > 0:
        GPIO.output(IN1_PIN, GPIO.HIGH)
        GPIO.output(IN2_PIN, GPIO.LOW)
    else:
        GPIO.output(IN1_PIN, GPIO.LOW)
        GPIO.output(IN2_PIN, GPIO.HIGH)

    # Set kecepatan (0 - 100%)
    pwm_obj.ChangeDutyCycle(abs(speed))

def main():
    global encoder_ticks
    print("[TEST] Menginisialisasi Pin GPIO Raspberry Pi...")

    # Setup GPIO
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    
    # Setup Pin Motor
    GPIO.setup(PWM_PIN, GPIO.OUT)
    GPIO.setup(IN1_PIN, GPIO.OUT)
    GPIO.setup(IN2_PIN, GPIO.OUT)
    
    # Setup Pin Encoder (dengan Internal Pull-Up)
    GPIO.setup(ENCA_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(ENCB_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    # Interrupt Encoder (Tembak callback saat Phase A naik)
    GPIO.add_event_detect(ENCA_PIN, GPIO.RISING, callback=encoder_callback)

    # Inisialisasi PWM di 1000 Hz
    motor_pwm = GPIO.PWM(PWM_PIN, 1000)
    motor_pwm.start(0)

    # Setup Network GCS
    config_path = os.path.join(ship_system_root, "config", "low_level_config.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    net = NetBridge(gcs_ip=config["network"]["gcs_ip"], udp_port=config["network"]["telemetry_port"])
    print("[TEST] Sistem Siap! Kontrol Ballast pakai Joystick GCS.\n")

    try:
        while True:
            # Baca perintah dari GCS
            gcs_commands = net.receive_commands() or {}
            
            blst_cmd = gcs_commands.get('ballast_cmd', gcs_commands.get('ballast', 0))
            z_cmd = gcs_commands.get('zero_encoder', False)

            if z_cmd:
                encoder_ticks = 0

            # Normalisasi kecepatan -100 ke 100
            pwm_speed = max(-100, min(100, int(blst_cmd)))
            
            # Eksekusi putaran motor
            set_motor(motor_pwm, pwm_speed)

            # Print ke layar
            print(f"\r\033[K[RASPI GPIO] ENC: {encoder_ticks:5} | PWM: {pwm_speed:4}% | Zero Btn: {z_cmd}", end="", flush=True)

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n\n[TEST] Dihentikan. Mematikan motor...")
    finally:
        set_motor(motor_pwm, 0)
        motor_pwm.stop()
        GPIO.cleanup()
        net.close()
        print("[TEST] GPIO Bersih. Selesai.")

if __name__ == "__main__":
    main()
