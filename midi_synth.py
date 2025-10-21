#!/usr/bin/env python3
"""
Arduino MIDI Synthesizer Controller
Sends MIDI notes to Arduino via serial communication
"""

import serial
import time
import argparse
import sys
from threading import Thread, Event

class ArduinoSynth:
    def __init__(self, port='/dev/cu.usbmodem1101', baud_rate=9600):
        self.port = port
        self.baud_rate = baud_rate
        self.arduino = None
        self.connected = False
        
    def connect(self):
        """Connect to Arduino"""
        try:
            self.arduino = serial.Serial(self.port, self.baud_rate, timeout=1)
            time.sleep(2)  # Wait for Arduino to initialize
            self.connected = True
            print(f"Connected to Arduino on {self.port}")
            return True
        except serial.SerialException as e:
            print(f"Failed to connect to Arduino: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Arduino"""
        if self.arduino and self.connected:
            self.arduino.close()
            self.connected = False
            print("Disconnected from Arduino")
    
    def midi_to_frequency(self, midi_note):
        """Convert MIDI note number to frequency in Hz"""
        # A4 (MIDI note 69) = 440 Hz
        return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))
    
    def play_note(self, frequency, duration_ms=500):
        """Send note command to Arduino"""
        if not self.connected:
            print("Not connected to Arduino")
            return
        
        command = f"{int(frequency)},{duration_ms}\n"
        try:
            self.arduino.write(command.encode())
            print(f"Playing: {int(frequency)}Hz for {duration_ms}ms")
        except serial.SerialException as e:
            print(f"Error sending command: {e}")
    
    def play_midi_note(self, midi_note, duration_ms=500):
        """Play a MIDI note number"""
        frequency = self.midi_to_frequency(midi_note)
        self.play_note(frequency, duration_ms)
    
    def play_sequence(self, notes, note_duration=500, pause_duration=100):
        """Play a sequence of MIDI notes"""
        for note in notes:
            if isinstance(note, tuple):
                midi_note, duration = note
            else:
                midi_note, duration = note, note_duration
            
            self.play_midi_note(midi_note, duration)
            time.sleep((duration + pause_duration) / 1000.0)
    
    def play_chord(self, chord_notes, duration_ms=1000):
        """Play multiple notes simultaneously (limited by single tone() function)"""
        print(f"Playing chord: {chord_notes}")
        for i, note in enumerate(chord_notes):
            delay = i * 50  # Slight delay between notes for chord effect
            frequency = self.midi_to_frequency(note)
            
            def delayed_note():
                time.sleep(delay / 1000.0)
                self.play_note(frequency, duration_ms - delay)
            
            Thread(target=delayed_note).start()

def demo_scales(synth):
    """Demo function to play various scales"""
    print("\n--- Playing C Major Scale ---")
    c_major = [60, 62, 64, 65, 67, 69, 71, 72]  # C4 to C5
    synth.play_sequence(c_major)
    
    time.sleep(1)
    
    print("\n--- Playing Minor Pentatonic ---")
    minor_pent = [60, 63, 65, 67, 70, 72]  # C minor pentatonic
    synth.play_sequence(minor_pent)
    
    time.sleep(1)
    
    print("\n--- Playing Chord Progression ---")
    chords = [
        [60, 64, 67],  # C major
        [57, 60, 64],  # A minor  
        [62, 65, 69],  # D minor
        [67, 71, 74],  # G major
    ]
    
    for chord in chords:
        synth.play_chord(chord, 800)
        time.sleep(1)

def interactive_mode(synth):
    """Interactive mode for playing notes"""
    print("\n--- Interactive Mode ---")
    print("Enter MIDI note numbers (0-127), 'q' to quit, 'demo' for demo")
    print("Format: 'note' or 'note,duration_ms'")
    
    while True:
        try:
            user_input = input("Note > ").strip()
            
            if user_input.lower() == 'q':
                break
            elif user_input.lower() == 'demo':
                demo_scales(synth)
                continue
            
            if ',' in user_input:
                note_str, duration_str = user_input.split(',', 1)
                note = int(note_str.strip())
                duration = int(duration_str.strip())
            else:
                note = int(user_input)
                duration = 500
            
            if 0 <= note <= 127:
                synth.play_midi_note(note, duration)
            else:
                print("MIDI note must be between 0 and 127")
                
        except ValueError:
            print("Invalid input. Use format: 'note' or 'note,duration'")
        except KeyboardInterrupt:
            print("\nExiting...")
            break

def main():
    parser = argparse.ArgumentParser(description='Arduino MIDI Synthesizer Controller')
    parser.add_argument('--port', '-p', default='/dev/cu.usbmodem1101', 
                       help='Arduino serial port')
    parser.add_argument('--baud', '-b', type=int, default=9600,
                       help='Baud rate')
    parser.add_argument('--demo', '-d', action='store_true',
                       help='Run demo sequence')
    parser.add_argument('--interactive', '-i', action='store_true',
                       help='Interactive mode')
    
    args = parser.parse_args()
    
    # Create synth instance
    synth = ArduinoSynth(args.port, args.baud)
    
    # Connect to Arduino
    if not synth.connect():
        sys.exit(1)
    
    try:
        if args.demo:
            demo_scales(synth)
        elif args.interactive:
            interactive_mode(synth)
        else:
            # Default behavior - play a simple melody
            print("Playing default melody...")
            melody = [60, 62, 64, 65, 67, 69, 71, 72]  # C major scale
            synth.play_sequence(melody)
            
    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        synth.disconnect()

if __name__ == "__main__":
    main()
