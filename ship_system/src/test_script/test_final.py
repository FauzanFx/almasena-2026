from pymavlink import mavutil
import time

# 1. Koneksi ke Pix32 / Pixhawk
port = "/dev/ttyACM0"
print(f"Connecting to Pix32 at {port}...")
master = mavutil.mavlink_connection(port, baud=115200)

print("Waiting for Heartbeat...")
master.wait_heartbeat()
target_sys = master.target_system if master.target_system else 1
target_comp = master.target_component if master.target_component else 1
print(f"Heartbeat OK! System {target_sys} Component {target_comp}")

# 2. Set Flight Mode ke MANUAL & ARMING
print("Setting Mode to MANUAL...")
master.set_mode('MANUAL')
time.sleep(1)

print("Arming Pix32...")
master.mav.command_long_send(
    target_sys, target_comp,
    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
    0, 1.0, 21963, 0, 0, 0, 0, 0  # Magic Force Arm Code
)
time.sleep(1)

# 3. Sinyal Netral (1500us) - Wajib agar ESC Unlock
print("Sending Neutral Signal (1500us)...")
start_init = time.time()
while time.time() - start_init < 2.0:
    master.mav.rc_channels_override_send(
        target_sys, target_comp,
        1500, 1500, 1500, 1500,
        0, 0, 0, 0
    )
    time.sleep(0.05)

# 4. Spin Thruster Forward (1700us) - 3 Detik
print("\n>>> SPINNING THRUSTERS FORWARD (1700us) <<<")
start_time = time.time()
while time.time() - start_time < 3.0:
    master.mav.rc_channels_override_send(
        target_sys, target_comp,
        1700, 1700, 1700, 1700,  # Channel 1-4
        0, 0, 0, 0
    )
    time.sleep(0.05)

# 5. Spin Thruster Reverse (1300us) - 2 Detik (Tes Arah Terbalik)
print("\n>>> SPINNING THRUSTERS REVERSE (1300us) <<<")
start_time = time.time()
while time.time() - start_time < 2.0:
    master.mav.rc_channels_override_send(
        target_sys, target_comp,
        1300, 1300, 1300, 1300,  # Channel 1-4
        0, 0, 0, 0
    )
    time.sleep(0.05)

# 6. Stop & DISARM
print("\n>>> STOPPING MOTORS & DISARMING... <<<")
master.mav.rc_channels_override_send(target_sys, target_comp, 1500, 1500, 1500, 1500, 0, 0, 0, 0)
master.mav.command_long_send(
    target_sys, target_comp,
    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
    0, 0.0, 0, 0, 0, 0, 0, 0
)
print("Test completed successfully!")
