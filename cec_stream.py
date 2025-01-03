#!/usr/bin/python3

# Monitor HDMI-CEC for volume keys, send RC5-encoded commands.
# Confirmed working with:
#   Cambridge Audio azur CX60A
#   Sony EX600 TV

#############
# CONSTANTS #
#############
VOL_UP = "key pressed: volume up (41)"
VOL_DN = "key pressed: volume down (42)"
MUTE = "key released: mute (43)"
READY = "audio status '7f'"  # message sent by cec-client to TV at end of handshaking

VOL_STEPS = 1
POWER_ON_DELAY = 5  # Delay in seconds after power on before sending commands

PIN = 4  # CPU GPIO number (not physical IO header pin number)

RC5_PER = 889  # half-bit period (microseconds)
CA_RC5_SYS = 16

MUTE_STATE = False  # False = unmuted, True = muted

# dictionary of possible commands, mapped to the code we need to send
cmd = {
    "vol-": 17,
    "vol+": 16,
    "mute": 13,
    "standby": 12,
    "bright": 72,
    "source+": 99,
    "source-": 126,
    "clipoff": 21,
    "clipon": 22,
    "muteon": 50,
    "muteoff": 51,
    "ampon": 110,
    "ampoff": 111,
}

#############
# Functions #
#############

def build_rc5(sys, cmd):
    """Build RC5 message, return as int"""
    RC5_START = 0b100 + (0b010 * (cmd < 64))
    RC5_SYS = int(sys)
    RC5_CMD = int(cmd)

    # RC-5 message has a 3-bit start sequence, a 5-bit system ID, and a 6-bit command.
    RC5_MSG = (
        ((RC5_START & 0b111) << 11) | ((RC5_SYS & 0b11111) << 6) | (RC5_CMD & 0b111111)
    )

    return RC5_MSG

def wave_mnch(DATA, PIN, PERIOD):
    """Manchester encode waveform. Period is the half-bit period in microseconds."""
    pi.set_mode(PIN, pigpio.OUTPUT)  # set GPIO pin to output.

    # create msg
    # syntax: pigpio.pulse(gpio_on, gpio_off, delay us)
    msg = []
    for i in bin(DATA)[2:]:  # iterate over bits
        if i == "1":
            msg.append(pigpio.pulse(0, 1 << PIN, PERIOD))  # L
            msg.append(pigpio.pulse(1 << PIN, 0, PERIOD))  # H
        else:
            msg.append(pigpio.pulse(1 << PIN, 0, PERIOD))  # H
            msg.append(pigpio.pulse(0, 1 << PIN, PERIOD))  # L

    msg.append(pigpio.pulse(0, 1 << PIN, PERIOD))  # return line to idle condition.
    pi.wave_add_generic(msg)
    try:
        wid = pi.wave_create()
        return wid
    except pigpio.error:
        pi.wave_clear()  # Clear all waves if we hit an error
        wid = pi.wave_create()  # Try again
        return wid

def send_command(command_type, repeat=1):
    """Send a command, managing wave resources properly"""
    try:
        wave_id = wave_mnch(build_rc5(CA_RC5_SYS, cmd[command_type]), PIN, RC5_PER)
        print(f"{command_type}")  # Print the command being sent
        for _ in range(repeat):
            pi.wave_send_once(wave_id)
            time.sleep(0.1)  # Small delay between sends
        
        # Wait for transmission to complete
        while pi.wave_tx_busy():
            time.sleep(0.01)
            
        # Clean up
        pi.wave_delete(wave_id)
    except pigpio.error as e:
        print(f"Error sending command {command_type}: {e}")
        pi.wave_clear()  # Reset wave resources

##############
# Start here #
##############

import pigpio
import sys
import subprocess
import time

pi = pigpio.pi()

# Clear any existing waves at startup
pi.wave_clear()

# run cec-client and watch output
p = subprocess.Popen(
    args=["/usr/bin/cec-client", "--type", "a", "RPI"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    universal_newlines=True,
)

while p.poll() is None:
    l = p.stdout.readline()
    print(l)
    # Handle TV power state changes
    if "TV (0): power status changed" in l:
        # Extract the final state by taking the last quoted string
        parts = l.split("'")
        final_state = parts[-2] if len(parts) >= 2 else ""
        
        # Turn amp on for 'on' state or transition to on
        if final_state == "on" or final_state == "in transition from standby to on":
            time.sleep(POWER_ON_DELAY)  # Wait before sending power on command
            send_command("ampon", repeat=4)
            MUTE_STATE = False  # Amp always turns on unmuted
            p.stdin.write(
                "tx 50:72:01 \n"  # tell TV "Audio System Active"
            )
            p.stdin.flush()
            
        # Turn amp off for standby state
        elif final_state == "standby":
            send_command("ampoff", repeat=4)
    
    # Handle any playback device power status changes
    elif ": power status changed from" in l:
        print("DEBUG: Detect power status change:", l)
        if "from 'on' to 'standby'" in l:
            send_command("ampoff", repeat=4)
        elif "from 'standby' to 'on'" in l:
            time.sleep(POWER_ON_DELAY)  # Wait before sending power on command
            send_command("ampon", repeat=4)
            MUTE_STATE = False  # Amp always turns on unmuted
            p.stdin.write(
                "tx 50:72:01 \n"  # tell TV "Audio System Active"
            )
            p.stdin.flush()
    elif READY in l:
        p.stdin.write("tx 50:7a:08 \n")  # report vol level 08
        p.stdin.flush()
    elif VOL_UP in l:
        p.stdin.write("tx 50:7a:10 \n")  # report vol level 16
        p.stdin.flush()
        send_command("vol+", repeat=VOL_STEPS)
    elif VOL_DN in l:
        p.stdin.write("tx 50:7a:04 \n")  # report vol level 04
        p.stdin.flush()
        send_command("vol-", repeat=VOL_STEPS)
    elif MUTE in l:
        if MUTE_STATE:
            # Currently muted, so unmute
            send_command("muteoff")
        else:
            # Currently unmuted, so mute
            send_command("muteon")
        MUTE_STATE = not MUTE_STATE  # Toggle the state

# Clean up when exiting
pi.wave_clear()
pi.stop()
sys.exit(0)
