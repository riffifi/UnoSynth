#!/usr/bin/env python3
"""
Arduino MIDI File Player
Reads MIDI files and plays them on Arduino synthesizer via serial
"""

import serial
import time
import mido
import argparse
import sys
import os
from pathlib import Path

class ArduinoMidiPlayer:
    def __init__(self, port='/dev/cu.usbmodem1101', baud_rate=9600):
        self.port = port
        self.baud_rate = baud_rate
        self.arduino = None
        self.connected = False
        self.playing = False
        
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
            # Send stop command to Arduino
            self.send_command("STOP")
            self.arduino.close()
            self.connected = False
            print("Disconnected from Arduino")
    
    def send_command(self, command):
        """Send command to Arduino"""
        if not self.connected:
            return False
        try:
            self.arduino.write(f"{command}\n".encode())
            return True
        except serial.SerialException as e:
            print(f"Error sending command: {e}")
            return False
    
    def midi_to_frequency(self, midi_note):
        """Convert MIDI note number to frequency in Hz"""
        return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))
    
    def play_note(self, midi_note, duration_ms):
        """Play a single MIDI note"""
        frequency = self.midi_to_frequency(midi_note)
        command = f"{int(frequency)},{int(duration_ms)}"
        return self.send_command(command)
    
    def play_midi_file(self, midi_file_path, tempo_multiplier=1.0, loop=False, track_filter=None, note_filter=None):
        """Play a MIDI file on the Arduino"""
        if not os.path.exists(midi_file_path):
            print(f"MIDI file not found: {midi_file_path}")
            return False
        
        try:
            midi_file = mido.MidiFile(midi_file_path)
        except Exception as e:
            print(f"Error loading MIDI file: {e}")
            return False
        
        print(f"Playing MIDI file: {midi_file_path}")
        print(f"Duration: {midi_file.length:.2f} seconds")
        print(f"Tracks: {len(midi_file.tracks)}")
        print(f"Tempo multiplier: {tempo_multiplier}x")
        if loop:
            print("Looping enabled - press Ctrl+C to stop")
        
        # Analyze tracks to help user choose
        self._analyze_tracks(midi_file)
        
        self.playing = True
        
        try:
            while True:
                self._play_midi_once(midi_file, tempo_multiplier, track_filter, note_filter)
                if not loop:
                    break
                print("Looping...")
                time.sleep(1)  # Brief pause between loops
                
        except KeyboardInterrupt:
            print("\nPlayback stopped by user")
        finally:
            self.playing = False
            self.send_command("STOP")
    
    def _analyze_tracks(self, midi_file):
        """Analyze MIDI tracks and show information"""
        print("\nTrack Analysis:")
        for i, track in enumerate(midi_file.tracks):
            note_count = 0
            note_range = [127, 0]  # min, max
            
            for msg in track:
                if msg.type == 'note_on' and msg.velocity > 0:
                    note_count += 1
                    note_range[0] = min(note_range[0], msg.note)
                    note_range[1] = max(note_range[1], msg.note)
            
            if note_count > 0:
                print(f"  Track {i}: {note_count} notes, range {note_range[0]}-{note_range[1]} ({self._note_name(note_range[0])}-{self._note_name(note_range[1])})")
            else:
                print(f"  Track {i}: No notes (probably metadata/drums)")
    
    def _note_name(self, midi_note):
        """Convert MIDI note to name"""
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        octave = (midi_note // 12) - 1
        note = notes[midi_note % 12]
        return f"{note}{octave}"
    
    def _play_midi_once(self, midi_file, tempo_multiplier, track_filter=None, note_filter=None):
        """Play MIDI file once with better monophonic handling"""
        # Extract notes from specified tracks or all tracks
        notes = []
        current_tempo = 500000  # Default MIDI tempo (microseconds per quarter note)
        
        tracks_to_process = [track_filter] if track_filter is not None else range(len(midi_file.tracks))
        
        for track_idx in tracks_to_process:
            if track_idx >= len(midi_file.tracks):
                continue
                
            track = midi_file.tracks[track_idx]
            current_time = 0
            
            for msg in track:
                current_time += msg.time
                
                # Update tempo if we encounter a tempo change
                if msg.type == 'set_tempo':
                    current_tempo = msg.tempo
                
                # Only process note_on events with velocity > 0
                if msg.type == 'note_on' and msg.velocity > 0:
                    # Skip drum notes (channel 9, typically notes 35-81)
                    if hasattr(msg, 'channel') and msg.channel == 9:
                        continue
                    
                    # Filter notes if specified
                    if note_filter and not (note_filter[0] <= msg.note <= note_filter[1]):
                        continue
                    
                    time_seconds = mido.tick2second(current_time, midi_file.ticks_per_beat, current_tempo)
                    notes.append((time_seconds, msg.note, msg.velocity))
        
        # Sort notes by time
        notes.sort(key=lambda x: x[0])
        
        # Remove overlapping notes (keep only the highest velocity note at each time)
        filtered_notes = []
        last_time = -1
        time_tolerance = 0.05  # 50ms tolerance for "simultaneous" notes
        
        for note_time, note, velocity in notes:
            # If this note is very close in time to the last one, only keep the louder one
            if filtered_notes and abs(note_time - last_time) < time_tolerance:
                if velocity > filtered_notes[-1][2]:  # This note is louder
                    filtered_notes[-1] = (note_time, note, velocity)
            else:
                filtered_notes.append((note_time, note, velocity))
                last_time = note_time
        
        print(f"\nPlaying {len(filtered_notes)} notes...")
        
        # Play the filtered notes
        start_time = time.time()
        
        for i, (note_time, note, velocity) in enumerate(filtered_notes):
            # Wait until it's time for this note
            target_time = note_time / tempo_multiplier
            current_time = time.time() - start_time
            
            if target_time > current_time:
                time.sleep(target_time - current_time)
            
            # Calculate note duration based on gap to next note
            if i < len(filtered_notes) - 1:
                next_note_time = filtered_notes[i + 1][0] / tempo_multiplier
                note_duration = max(100, min(1000, int((next_note_time - target_time) * 1000 * 0.9)))
            else:
                note_duration = 500  # Default for last note
            
            # Play the note
            self.play_note(note, note_duration)
            print(f"♪ {self._note_name(note)} ({self.midi_to_frequency(note):.1f}Hz) for {note_duration}ms")
    
    def list_available_ports(self):
        """List available serial ports"""
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        print("Available serial ports:")
        for port in ports:
            print(f"  {port.device} - {port.description}")

def find_midi_files(directory="."):
    """Find MIDI files in the specified directory"""
    midi_extensions = ['.mid', '.midi', '.MID', '.MIDI']
    midi_files = []
    
    path = Path(directory)
    for ext in midi_extensions:
        midi_files.extend(path.glob(f"*{ext}"))
    
    return sorted(midi_files)

def main():
    parser = argparse.ArgumentParser(description='Arduino MIDI File Player')
    parser.add_argument('--port', '-p', default='/dev/cu.usbmodem1101', 
                       help='Arduino serial port')
    parser.add_argument('--baud', '-b', type=int, default=9600,
                       help='Baud rate')
    parser.add_argument('--file', '-f', type=str,
                       help='MIDI file to play')
    parser.add_argument('--tempo', '-t', type=float, default=1.0,
                       help='Tempo multiplier (1.0 = normal speed)')
    parser.add_argument('--loop', '-l', action='store_true',
                       help='Loop the MIDI file indefinitely')
    parser.add_argument('--list-ports', action='store_true',
                       help='List available serial ports')
    parser.add_argument('--list-files', action='store_true',
                       help='List MIDI files in current directory')
    
    args = parser.parse_args()
    
    # Create player instance
    player = ArduinoMidiPlayer(args.port, args.baud)
    
    if args.list_ports:
        player.list_available_ports()
        return
    
    if args.list_files:
        midi_files = find_midi_files()
        print("MIDI files in current directory:")
        for f in midi_files:
            print(f"  {f}")
        return
    
    # Connect to Arduino
    if not player.connect():
        sys.exit(1)
    
    try:
        if args.file:
            # Play specified file
            player.play_midi_file(args.file, args.tempo, args.loop)
        else:
            # Interactive mode - let user choose from available files
            midi_files = find_midi_files()
            if not midi_files:
                print("No MIDI files found in current directory.")
                print("Place some .mid or .midi files here, or specify a file with --file")
                return
            
            print("Available MIDI files:")
            for i, f in enumerate(midi_files, 1):
                print(f"  {i}. {f.name}")
            
            while True:
                try:
                    choice = input("\nEnter file number (or 'q' to quit): ").strip()
                    if choice.lower() == 'q':
                        break
                    
                    file_idx = int(choice) - 1
                    if 0 <= file_idx < len(midi_files):
                        selected_file = midi_files[file_idx]
                        print(f"\nSelected: {selected_file.name}")
                        player.play_midi_file(str(selected_file), args.tempo, args.loop)
                    else:
                        print("Invalid selection")
                        
                except ValueError:
                    print("Please enter a valid number")
                except KeyboardInterrupt:
                    print("\nExiting...")
                    break
                    
    finally:
        player.disconnect()

if __name__ == "__main__":
    main()
