#!/usr/bin/env python3
"""
Test script for pitch bend and command queue improvements
Demonstrates guitar-style bends and dense note sequences
"""

import serial
import time
import sys

def test_command_queue(arduino):
    """Test command queue by sending rapid fire commands"""
    print("\n=== Testing Command Queue (Rapid Notes) ===")
    print("Sending 20 rapid notes to test queue buffering...")
    
    # Send rapid sequence of notes
    notes = [60, 62, 64, 65, 67, 69, 71, 72, 71, 69, 67, 65, 64, 62, 60, 58, 56, 55, 53, 51]
    for i, note in enumerate(notes):
        freq = 440.0 * (2.0 ** ((note - 69) / 12.0))
        # Very short duration to stress test the queue
        arduino.write(f"FREQ,{freq:.2f},100,{i % 2},200\n".encode())
        time.sleep(0.05)  # 50ms between commands (faster than note duration)
        print(f"  Sent note {i+1}/20: MIDI {note} ({freq:.1f}Hz)")
    
    print("✓ Command queue test complete (check if all notes played without drops)")

def test_pitch_bend(arduino):
    """Test pitch bend functionality"""
    print("\n=== Testing Pitch Bend (Guitar-Style Bends) ===")
    
    # Test 1: Simple whole-step bend up
    print("\n1. Whole-step bend up (E4 -> F#4):")
    base_note = 64  # E4
    target_note = 66  # F#4
    base_freq = 440.0 * (2.0 ** ((base_note - 69) / 12.0))
    target_freq = 440.0 * (2.0 ** ((target_note - 69) / 12.0))
    
    # Play base note
    cmd = f"FREQ,{base_freq:.2f},1500,0,200\n"
    print(f"   Sending: {cmd.strip()}")
    arduino.write(cmd.encode())
    time.sleep(0.5)  # Give note time to start
    
    # Check Arduino response
    while arduino.in_waiting > 0:
        print(f"   Arduino: {arduino.readline().decode().strip()}")
    
    # Bend up over 500ms
    cmd = f"BEND,0,{target_freq:.2f},500\n"
    print(f"   Sending: {cmd.strip()}")
    arduino.write(cmd.encode())
    time.sleep(0.6)
    
    # Check Arduino response
    while arduino.in_waiting > 0:
        print(f"   Arduino: {arduino.readline().decode().strip()}")
    
    time.sleep(0.5)
    
    # Stop all channels before test 2
    print("\n   Stopping all channels...")
    arduino.write(b"STOP\n")
    time.sleep(0.3)
    
    # Test 2: Bend down
    print("\n2. Whole-step bend down (G4 -> F4):")
    base_note = 67  # G4
    target_note = 65  # F4
    base_freq = 440.0 * (2.0 ** ((base_note - 69) / 12.0))
    target_freq = 440.0 * (2.0 ** ((target_note - 69) / 12.0))
    
    cmd = f"FREQ,{base_freq:.2f},2000,1,200\n"
    print(f"   Sending: {cmd.strip()}")
    arduino.write(cmd.encode())
    time.sleep(0.5)  # Give note time to start
    
    # Check Arduino response
    while arduino.in_waiting > 0:
        print(f"   Arduino: {arduino.readline().decode().strip()}")
    
    cmd = f"BEND,1,{target_freq:.2f},500\n"
    print(f"   Sending: {cmd.strip()}")
    arduino.write(cmd.encode())
    time.sleep(0.6)
    
    # Check Arduino response
    while arduino.in_waiting > 0:
        print(f"   Arduino: {arduino.readline().decode().strip()}")
    
    time.sleep(0.5)
    
    # Stop all channels before test 3
    print("\n   Stopping all channels...")
    arduino.write(b"STOP\n")
    time.sleep(0.3)
    
    # Test 3: Vibrato (rapid small bends)
    print("\n3. Vibrato effect (A4 with ±0.5 semitone oscillation):")
    base_note = 69  # A4
    base_freq = 440.0
    
    arduino.write(f"FREQ,{base_freq:.2f},5000,0,200\n".encode())
    print(f"   Playing A4 ({base_freq:.1f}Hz) with vibrato")
    time.sleep(0.5)
    
    # Create vibrato by oscillating pitch
    # Slower vibrato with longer bend times
    for i in range(6):
        # Bend up 0.5 semitones
        bent_freq = 440.0 * (2.0 ** (0.5 / 12.0))
        arduino.write(f"BEND,0,{bent_freq:.2f},200\n".encode())
        time.sleep(0.25)  # Wait for bend to mostly complete
        
        # Bend down 0.5 semitones (back through center)
        bent_freq = 440.0 * (2.0 ** (-0.5 / 12.0))
        arduino.write(f"BEND,0,{bent_freq:.2f},200\n".encode())
        time.sleep(0.25)
    
    # Return to center
    arduino.write(f"BEND,0,{base_freq:.2f},150\n".encode())
    time.sleep(1.0)
    
    print("✓ Pitch bend test complete")

def test_blues_lick(arduino):
    """Play a blues guitar lick with bends"""
    print("\n=== Testing Blues Guitar Lick with Bends ===")
    
    # Blues pentatonic lick with bends
    # Pattern: A4 -> C5 (with bend) -> Bb4 -> A4 -> G4 (with bend up) -> A4
    lick = [
        (69, 300, None),      # A4
        (70, 500, 72),        # Bb4 -> bend to C5
        (70, 300, None),      # Bb4 (release bend)
        (69, 300, None),      # A4
        (67, 500, 69),        # G4 -> bend to A4
        (69, 500, None)       # A4
    ]
    
    print("Playing blues lick on left channel...")
    for note, duration, bend_to in lick:
        freq = 440.0 * (2.0 ** ((note - 69) / 12.0))
        arduino.write(f"FREQ,{freq:.2f},{duration},0,200\n".encode())
        note_name = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'][note % 12]
        octave = (note // 12) - 1
        
        if bend_to:
            time.sleep(0.1)  # Let note start
            bend_freq = 440.0 * (2.0 ** ((bend_to - 69) / 12.0))
            arduino.write(f"BEND,0,{bend_freq:.2f},300\n".encode())
            bend_note_name = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'][bend_to % 12]
            bend_octave = (bend_to // 12) - 1
            print(f"   {note_name}{octave} -> BEND -> {bend_note_name}{bend_octave}")
        else:
            print(f"   {note_name}{octave}")
        
        time.sleep(duration / 1000.0)
    
    print("✓ Blues lick test complete")

def main():
    # Default port for Linux/Debian
    port = '/dev/ttyUSB0'
    
    # Check command line argument for custom port
    if len(sys.argv) > 1:
        port = sys.argv[1]
    
    print(f"Connecting to Arduino on {port}...")
    
    try:
        arduino = serial.Serial(port, 9600, timeout=1)
        time.sleep(2)  # Wait for Arduino to initialize
        print("✓ Connected!")
        
        # Read any startup messages
        print("\n--- Arduino Startup Messages ---")
        time.sleep(0.5)
        while arduino.in_waiting > 0:
            print(arduino.readline().decode().strip())
        print("--- End Startup Messages ---")
        
        # Run tests
        test_command_queue(arduino)
        time.sleep(1)
        
        test_pitch_bend(arduino)
        time.sleep(1)
        
        test_blues_lick(arduino)
        
        # Stop all
        print("\n=== Stopping all channels ===")
        arduino.write(b"STOP\n")
        
        arduino.close()
        print("\n✓ All tests complete!")
        
    except serial.SerialException as e:
        print(f"Error: Could not connect to Arduino on {port}")
        print(f"Details: {e}")
        print(f"\nUsage: python3 test_bend.py [port]")
        print(f"Example: python3 test_bend.py /dev/ttyACM0")
        sys.exit(1)

if __name__ == "__main__":
    main()
