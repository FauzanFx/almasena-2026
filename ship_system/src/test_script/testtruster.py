from pymavlink import mavutil
import time

port = "/dev/ttyACM0"
print(f"Connecting to Pix32 at {port}...")
master = mavutil.mavlink_connection(port, baud=115200)

print("Waiting for Heartbeat...")
master.wait_heartbeat()
target_sys = master.target_system if master.target_system else 1
target_comp = master.target_component if master.target_component else 1

# Force ARM
master.set_mode('MANUAL')
master.mav.command_long_send(
    target_sys, target_comp,
    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
    0, 1.0, 21963, 0, 0, 0, 0, 0
)
time.sleep(1)

# Coba Uji Titik Netral 1000us, 1100us, 1500us
test_pwms = [1000, 1100, 1500]

for pwm_netral in test_pwms:
    print(f"\n--- MENGUJI TITIK NETRAL PWM: {pwm_netral} us ---")
    print("Dengarkan nada ESC... (Apakah ada nada konfirmasi/panjang?)")
    
    # Kirim PWM netral selama 2 detik
    start = time.time()
    while time.time() - start < 2.0:
        master.mav.rc_channels_override_send(
            target_sys, target_comp,
            pwm_netral, pwm_netral, pwm_netral, pwm_netral,
            0, 0, 0, 0
        )
        time.sleep(0.05)
        
    print(f"Mencoba memutar motor dengan {pwm_netral + 200} us (2 Detik)...")
    start = time.time()
    while time.time() - start < 2.0:
        master.mav.rc_channels_override_send(
            target_sys, target_comp,
            pwm_netral + 200, pwm_netral + 200, pwm_netral + 200, pwm_netral + 200,
            0, 0, 0, 0
        )
        time.sleep(0.05)

# Stop
master.mav.rc_channels_override_send(target_sys, target_comp, 1500, 1500, 1500, 1500, 0, 0, 0, 0)
master.mav.command_long_send(target_sys, target_comp, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0.0, 0, 0, 0, 0, 0, 0)
print("\nSelesai.")
