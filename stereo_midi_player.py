#!/usr/bin/env python3
"""
Arduino Stereo MIDI Player
Plays MIDI files using two channels on Arduino for richer sound
"""

import serial
import time
import mido
import argparse
import sys
import os
from pathlib import Path
import random

class ArduinoStereoPlayer:
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
            print(f"Connected to Arduino Stereo Synth on {self.port}")
            return True
        except serial.SerialException as e:
            print(f"Failed to connect to Arduino: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Arduino"""
        if self.arduino and self.connected:
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
    
    def play_note_on_channel(self, midi_note, duration_ms, channel):
        """Play a MIDI note on specific channel (0=left, 1=right)"""
        frequency = self.midi_to_frequency(midi_note)
        command = f"NOTE,{midi_note},{duration_ms},{channel}"
        return self.send_command(command)
    
    def play_chord(self, note1, note2, duration_ms):
        """Play two notes simultaneously as a chord"""
        command = f"CHORD,{note1},{note2},{duration_ms}"
        return self.send_command(command)
    
    def play_mono_note(self, midi_note, duration_ms):
        """Play the same note on both channels simultaneously (true mono)"""
        command = f"MONO,{midi_note},{duration_ms}"
        return self.send_command(command)
    
    def stop_channel(self, channel=None):
        """Stop specific channel or both"""
        if channel is None:
            command = "STOP"
        else:
            command = f"STOP,{channel}"
        return self.send_command(command)
    
    def get_status(self):
        """Get synth status"""
        return self.send_command("STATUS")
    
    def play_stereo_midi_file(self, midi_file_path, tempo_multiplier=1.0, loop=False, 
                             stereo_mode="auto", bass_threshold=60):
        """Play MIDI file with stereo separation"""
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
        print(f"Stereo mode: {stereo_mode}")
        print(f"Bass threshold: {bass_threshold} (notes below go to left)")
        
        self.playing = True
        
        try:
            while True:
                self._play_stereo_once(midi_file, tempo_multiplier, stereo_mode, bass_threshold)
                if not loop:
                    break
                print("Looping...")
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\nPlayback stopped by user")
        finally:
            self.playing = False
            self.send_command("STOP")
    
    def _play_stereo_once(self, midi_file, tempo_multiplier, stereo_mode, bass_threshold):
        """Play MIDI file once with stereo processing"""
        # Extract and process notes
        notes = self._extract_notes(midi_file)
        stereo_notes = self._assign_stereo_channels(notes, stereo_mode, bass_threshold)
        
        print(f"\nPlaying {len(stereo_notes)} stereo events...")
        
        # Play the stereo notes
        start_time = time.time()
        
        for i, (note_time, events) in enumerate(stereo_notes):
            # Wait until it's time for this event
            target_time = note_time / tempo_multiplier
            current_time = time.time() - start_time
            
            if target_time > current_time:
                time.sleep(target_time - current_time)
            
            # Process all events at this time point
            for event in events:
                event_type = event['type']
                
                if event_type == 'note':
                    note = event['note']
                    duration = event['duration']
                    channel = event['channel']
                    self.play_note_on_channel(note, duration, channel)
                    channel_name = "LEFT" if channel == 0 else "RIGHT"
                    print(f"♪ {self._note_name(note)} ({channel_name}) for {duration}ms")
                
                elif event_type == 'chord':
                    note1 = event['note1']
                    note2 = event['note2']
                    duration = event['duration']
                    self.play_chord(note1, note2, duration)
                    print(f"♫ CHORD: {self._note_name(note1)} + {self._note_name(note2)} for {duration}ms")
                
                elif event_type == 'mono':
                    note = event['note']
                    duration = event['duration']
                    self.play_mono_note(note, duration)
                    print(f"♪♪ MONO: {self._note_name(note)} on BOTH channels for {duration}ms")
    
    def _extract_notes(self, midi_file):
        """Extract notes from MIDI file"""
        notes = []
        current_tempo = 500000  # Default MIDI tempo
        
        for track in midi_file.tracks:
            current_time = 0
            
            for msg in track:
                current_time += msg.time
                
                if msg.type == 'set_tempo':
                    current_tempo = msg.tempo
                
                if msg.type == 'note_on' and msg.velocity > 0:
                    # Skip drum channel
                    if hasattr(msg, 'channel') and msg.channel == 9:
                        continue
                    
                    time_seconds = mido.tick2second(current_time, midi_file.ticks_per_beat, current_tempo)
                    notes.append((time_seconds, msg.note, msg.velocity))
        
        return sorted(notes, key=lambda x: x[0])
    
    def _assign_stereo_channels(self, notes, stereo_mode, bass_threshold):
        """Assign notes to left/right channels and group simultaneous events"""
        stereo_events = []
        
        # Group notes by time (with small tolerance for "simultaneous" notes)
        time_groups = []
        current_group = []
        last_time = -1
        time_tolerance = 0.05  # 50ms tolerance
        
        for note_time, note, velocity in notes:
            if current_group and abs(note_time - last_time) > time_tolerance:
                time_groups.append((last_time, current_group))
                current_group = []
            
            current_group.append((note, velocity))
            last_time = note_time
        
        if current_group:
            time_groups.append((last_time, current_group))
        
        # Process each time group
        for i, (group_time, group_notes) in enumerate(time_groups):
            events = []
            
            # Calculate duration to next group
            if i < len(time_groups) - 1:
                next_time = time_groups[i + 1][0]
                base_duration = max(100, min(1000, int((next_time - group_time) * 1000 * 0.9)))
            else:
                base_duration = 500
            
            if len(group_notes) == 1:
                # Single note - assign channel based on mode
                note, velocity = group_notes[0]
                
                if stereo_mode in ['mono', 'sync']:
                    # Play same note on both channels for fuller sound using MONO command
                    events.append({
                        'type': 'mono',
                        'note': note,
                        'duration': base_duration
                    })
                else:
                    channel = self._assign_channel(note, stereo_mode, bass_threshold)
                    events.append({
                        'type': 'note',
                        'note': note,
                        'duration': base_duration,
                        'channel': channel
                    })
            
            elif len(group_notes) == 2:
                # Two notes - play as chord or separate channels
                note1, vel1 = group_notes[0]
                note2, vel2 = group_notes[1]
                
                if stereo_mode == "chord":
                    events.append({
                        'type': 'chord',
                        'note1': note1,
                        'note2': note2,
                        'duration': base_duration
                    })
                else:
                    # Assign to different channels
                    events.append({
                        'type': 'note',
                        'note': note1,
                        'duration': base_duration,
                        'channel': 0  # Left
                    })
                    events.append({
                        'type': 'note',
                        'note': note2,
                        'duration': base_duration,
                        'channel': 1  # Right
                    })
            
            else:
                # Multiple notes - select best two
                group_notes.sort(key=lambda x: x[1], reverse=True)  # Sort by velocity
                note1, vel1 = group_notes[0]  # Loudest
                note2, vel2 = group_notes[1]  # Second loudest
                
                events.append({
                    'type': 'chord',
                    'note1': note1,
                    'note2': note2,
                    'duration': base_duration
                })
            
            if events:
                stereo_events.append((group_time, events))
        
        return stereo_events
    
    def _assign_channel(self, note, stereo_mode, bass_threshold):
        """Assign a note to left (0) or right (1) channel"""
        if stereo_mode == "bass_split":
            return 0 if note < bass_threshold else 1
        elif stereo_mode == "random":
            return random.randint(0, 1)
        elif stereo_mode == "alternate":
            return note % 2
        else:  # "auto"
            return 0 if note < bass_threshold else 1
    
    def _note_name(self, midi_note):
        """Convert MIDI note to name"""
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        octave = (midi_note // 12) - 1
        note = notes[midi_note % 12]
        return f"{note}{octave}"

def demo_stereo_chords(player):
    """Demo stereo chord progression"""
    print("\n=== STEREO CHORD DEMO ===")
    
    # Play some nice chord progressions
    chords = [
        (60, 64),  # C + E
        (62, 65),  # D + F
        (64, 67),  # E + G
        (65, 69),  # F + A
        (67, 71),  # G + B
        (69, 72),  # A + C
    ]
    
    for note1, note2 in chords:
        print(f"Playing chord: {player._note_name(note1)} + {player._note_name(note2)}")
        player.play_chord(note1, note2, 800)


def main():
    parser = argparse.ArgumentParser(description='Arduino Stereo MIDI Player')
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
    parser.add_argument('--stereo-mode', choices=['auto', 'bass_split', 'chord', 'random', 'alternate', 'mono', 'sync'],
                       default='auto', help='Stereo mode: auto/bass_split=bass left, chord=harmony, mono/sync=same note both channels')
    parser.add_argument('--bass-threshold', type=int, default=60,
                       help='MIDI note threshold for bass (notes below go left)')
    parser.add_argument('--demo', action='store_true',
                       help='Run stereo chord demo')
    
    args = parser.parse_args()
    
    # Create player instance
    player = ArduinoStereoPlayer(args.port, args.baud)
    
    # Connect to Arduino
    if not player.connect():
        sys.exit(1)
    
    try:
        if args.demo:
            demo_stereo_chords(player)
        elif args.file:
            player.play_stereo_midi_file(args.file, args.tempo, args.loop, 
                                       args.stereo_mode, args.bass_threshold)
        else:
            print("No file specified. Use --file to specify a MIDI file or --demo for demo")
            
    finally:
        player.disconnect()

if __name__ == "__main__":
    main()
