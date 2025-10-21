#!/usr/bin/env python3
"""
Test script to debug mono audio issues
"""

import serial
import time
import sys

# Arduino connection
ARDUINO_PORT = '/dev/cu.usbmodem1101'  # Change this to your port
BAUD_RATE = 9600

def test_mono():
    try:
        print(f"Connecting to Arduino on {ARDUINO_PORT}...")
        arduino = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=2)
        time.sleep(2)
        print("Connected!")
        
        print("\n=== Testing individual channels ===")
        print("Testing LEFT channel (pin 9)...")
        arduino.write(b"NOTE,60,2000,0\n")  # C4 for 2 seconds on left
        time.sleep(3)
        
        print("Testing RIGHT channel (pin 10)...")
        arduino.write(b"NOTE,60,2000,1\n")  # C4 for 2 seconds on right
        time.sleep(3)
        
        print("\n=== Testing CHORD command ===")
        print("Testing CHORD with different notes...")
        arduino.write(b"CHORD,60,64,2000\n")  # C4 + E4 for 2 seconds
        time.sleep(3)
        
        print("\n=== Testing MONO command ===")
        print("Testing MONO command (same note both channels)...")
        arduino.write(b"MONO,60,2000\n")  # C4 for 2 seconds on both
        time.sleep(3)
        
        print("\n=== Testing manual simultaneous commands ===")
        print("Sending LEFT and RIGHT commands rapidly...")
        arduino.write(b"NOTE,60,2000,0\n")
        arduino.write(b"NOTE,60,2000,1\n")
        time.sleep(3)
        
        arduino.write(b"STOP\n")
        arduino.close()
        print("Test complete!")
        
    except serial.SerialException as e:
        print(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nTest interrupted")
        if 'arduino' in locals():
            arduino.write(b"STOP\n")
            arduino.close()

if __name__ == "__main__":
    test_mono()
