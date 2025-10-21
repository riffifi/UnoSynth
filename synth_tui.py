#!/usr/bin/env python3
"""
Beautiful TUI for Arduino MIDI Synthesizer
A modern terminal interface with real-time visualization and MIDI playback
"""

import serial
import time
import threading
import sys
import os
from pathlib import Path
import random
from datetime import datetime
import mido
import select
import termios
import tty

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.live import Live
from rich.align import Align
from rich import box

class ArduinoSynthTUI:
    def __init__(self, port='/dev/cu.usbmodem1101', baud_rate=9600):
        self.console = Console()
        self.port = port
        self.baud_rate = baud_rate
        self.arduino = None
        self.connected = False
        self.playing = False
        self.running = False
        self.browsing_files = False
        self.selected_file_index = 0
        
        # Status tracking
        self.current_file = None
        self.current_mode = "mono"
        self.tempo_multiplier = 1.0
        self.notes_played = 0
        self.start_time = None
        self.last_note = {"left": None, "right": None}
        self.channel_activity = {"left": False, "right": False}
        
        # TUI state
        self.layout = Layout()
        self.setup_layout()
        
    def setup_layout(self):
        """Setup the TUI layout"""
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        
        self.layout["main"].split_row(
            Layout(name="left_panel", ratio=1),
            Layout(name="center_panel", ratio=2),
            Layout(name="right_panel", ratio=1)
        )
        
        self.layout["left_panel"].split_column(
            Layout(name="connection", size=8),
            Layout(name="channels", size=10),
            Layout(name="controls")
        )
        
        self.layout["center_panel"].split_column(
            Layout(name="visualizer", size=12),
            Layout(name="file_info")
        )
        
        self.layout["right_panel"].split_column(
            Layout(name="stats", size=10),
            Layout(name="log")
        )
    
    def create_header(self):
        """Create the header panel"""
        title = Text("🎵 ARDUINO STEREO SYNTHESIZER 🎵", style="bold magenta")
        subtitle = Text("Real-time MIDI Player with Beautiful Visualization", style="italic cyan")
        
        header_text = Text()
        header_text.append(title)
        header_text.append("\n")
        header_text.append(subtitle)
        
        return Panel(
            Align.center(header_text),
            style="bright_blue",
            box=box.DOUBLE
        )
    
    def create_connection_panel(self):
        """Create connection status panel"""
        if self.connected:
            status = Text("🟢 CONNECTED", style="bold green")
            port_info = Text(f"Port: {self.port}", style="dim")
        else:
            status = Text("🔴 DISCONNECTED", style="bold red")
            port_info = Text("No connection", style="dim red")
        
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Label", style="bold")
        table.add_column("Value")
        
        table.add_row("Status:", status)
        table.add_row("Port:", port_info)
        table.add_row("Baud:", str(self.baud_rate))
        
        return Panel(
            table,
            title="🔌 Connection",
            border_style="green" if self.connected else "red"
        )
    
    def create_channels_panel(self):
        """Create channel activity panel"""
        left_color = "green" if self.channel_activity["left"] else "dim"
        right_color = "green" if self.channel_activity["right"] else "dim"
        
        left_note = self.last_note["left"] or "---"
        right_note = self.last_note["right"] or "---"
        
        table = Table(show_header=True, box=box.SIMPLE_HEAD)
        table.add_column("Channel", style="bold")
        table.add_column("Status")
        table.add_column("Note")
        
        left_status = "🔊 ACTIVE" if self.channel_activity["left"] else "🔇 IDLE"
        right_status = "🔊 ACTIVE" if self.channel_activity["right"] else "🔇 IDLE"
        
        table.add_row("LEFT", Text(left_status, style=left_color), Text(left_note, style=left_color))
        table.add_row("RIGHT", Text(right_status, style=right_color), Text(right_note, style=right_color))
        
        return Panel(
            table,
            title="🎶 Channels",
            border_style="blue"
        )
    
    def create_controls_panel(self):
        """Create controls information panel"""
        controls = [
            ("Q", "Quit"),
            ("Space", "Demo Note"),
            ("R", "Reset"),
            ("1-5", "Scale Notes"),
            ("C", "Chord"),
            ("M", "Play MIDI"),
            ("S", "Stop"),
        ]
        
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="bold cyan")
        table.add_column("Action", style="white")
        
        for key, action in controls:
            table.add_row(f"[{key}]", action)
        
        return Panel(
            table,
            title="⌨️  Controls",
            border_style="cyan"
        )
    
    def create_visualizer_panel(self):
        """Create music visualizer panel"""
        if not (self.channel_activity["left"] or self.channel_activity["right"]):
            viz_content = Align.center(
                Text("🎵 Press Space for Demo Note 🎵", style="dim italic"),
                vertical="middle"
            )
        else:
            # Create a simple ASCII visualizer
            bars = []
            for i in range(16):
                if self.channel_activity["left"] or self.channel_activity["right"]:
                    height = random.randint(3, 8)
                else:
                    height = 1
                bar = "█" * height + "░" * (8 - height)
                bars.append(bar)
            
            viz_lines = []
            for row in range(8):
                line = ""
                for bar in bars:
                    line += bar[row] + " "
                viz_lines.append(line)
            
            viz_text = Text("\n".join(viz_lines), style="bright_magenta")
            viz_content = Align.center(viz_text, vertical="middle")
        
        return Panel(
            viz_content,
            title="🎼 Audio Visualizer",
            border_style="magenta"
        )
    
    def create_file_info_panel(self):
        """Create file information panel"""
        if self.browsing_files:
            return self.create_midi_browser_panel()
        
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Label", style="bold")
        table.add_column("Value")
        
        table.add_row("Mode:", self.current_mode.upper())
        table.add_row("Tempo:", f"{self.tempo_multiplier}x")
        
        if self.current_file:
            table.add_row("File:", self.current_file)
        
        if self.playing:
            table.add_row("Status:", "🎵 Playing")
        
        if self.start_time:
            elapsed = int(time.time() - self.start_time)
            table.add_row("Uptime:", f"{elapsed//60:02d}:{elapsed%60:02d}")
        
        return Panel(
            table,
            title="📁 System Info",
            border_style="yellow"
        )
    
    def create_stats_panel(self):
        """Create statistics panel"""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Metric", style="bold")
        table.add_column("Value", style="cyan")
        
        table.add_row("Notes Played:", str(self.notes_played))
        table.add_row("Status:", "🎵 Demo Mode" if self.connected else "❌ Offline")
        
        # Show frequency info if playing
        if self.last_note["left"]:
            freq = self.midi_to_frequency(self.note_name_to_midi(self.last_note["left"]))
            table.add_row("Last Freq:", f"{freq:.1f} Hz")
        
        return Panel(
            table,
            title="📊 Statistics",
            border_style="green"
        )
    
    def create_log_panel(self):
        """Create log panel"""
        current_time = datetime.now().strftime('%H:%M:%S')
        
        log_entries = [
            f"{current_time} - System ready",
        ]
        
        if self.connected:
            log_entries.append(f"{current_time} - Arduino connected")
        else:
            log_entries.append(f"{current_time} - Waiting for Arduino")
        
        if self.notes_played > 0:
            log_entries.append(f"{current_time} - {self.notes_played} notes played")
        
        log_text = "\n".join(log_entries[-4:])  # Show last 4 entries
        
        return Panel(
            Text(log_text, style="dim"),
            title="📝 Activity Log",
            border_style="white"
        )
    
    def create_footer(self):
        """Create footer with help text"""
        help_text = Text()
        help_text.append("Press ", style="dim")
        help_text.append("[Q]", style="bold red")
        help_text.append(" to quit, ", style="dim")
        help_text.append("[Space]", style="bold cyan")
        help_text.append(" for demo note, ", style="dim")
        help_text.append("[1-5]", style="bold magenta")
        help_text.append(" for scale notes", style="dim")
        
        return Panel(
            Align.center(help_text),
            style="dim",
            box=box.SIMPLE
        )
    
    def update_display(self):
        """Update all panels"""
        self.layout["header"].update(self.create_header())
        self.layout["connection"].update(self.create_connection_panel())
        self.layout["channels"].update(self.create_channels_panel())
        self.layout["controls"].update(self.create_controls_panel())
        self.layout["visualizer"].update(self.create_visualizer_panel())
        self.layout["file_info"].update(self.create_file_info_panel())
        self.layout["stats"].update(self.create_stats_panel())
        self.layout["log"].update(self.create_log_panel())
        self.layout["footer"].update(self.create_footer())
    
    def play_midi_file(self, midi_file_path):
        """Play a MIDI file using mido with better playback"""
        if not self.connected:
            self.console.print("[red]Arduino not connected - cannot play MIDI file[/red]")
            return
            
        try:
            midi_file = mido.MidiFile(midi_file_path)
            self.playing = True
            
            # Extract notes for better playback
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
            
            # Sort notes by time
            notes.sort(key=lambda x: x[0])
            
            # Play the notes
            start_time = time.time()
            for i, (note_time, note, velocity) in enumerate(notes):
                if not self.playing or not self.running:
                    break
                    
                # Wait until it's time for this note
                target_time = note_time
                current_time = time.time() - start_time
                
                if target_time > current_time:
                    time.sleep(target_time - current_time)
                
                # Calculate note duration
                if i < len(notes) - 1:
                    next_note_time = notes[i + 1][0]
                    note_duration = max(100, min(1000, int((next_note_time - target_time) * 1000 * 0.9)))
                else:
                    note_duration = 500
                
                # Play the note
                self.play_mono_note(note, note_duration)
                
        except Exception as e:
            self.console.print(f"[red]Failed to play MIDI file:[/red] {str(e)}")
        finally:
            self.playing = False
    
    def connect(self):
        """Connect to Arduino"""
        try:
            self.arduino = serial.Serial(self.port, self.baud_rate, timeout=1)
            time.sleep(2)
            self.connected = True
            return True
        except serial.SerialException:
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from Arduino"""
        if self.arduino and self.connected:
            self.arduino.close()
            self.connected = False
    
    def send_command(self, command):
        """Send command to Arduino"""
        if not self.connected:
            return False
        try:
            self.arduino.write(f"{command}\n".encode())
            return True
        except serial.SerialException:
            return False
    
    def play_mono_note(self, midi_note, duration_ms):
        """Play mono note and update UI"""
        self.send_command(f"MONO,{midi_note},{duration_ms}")
        self.channel_activity["left"] = True
        self.channel_activity["right"] = True
        self.last_note["left"] = self._note_name(midi_note)
        self.last_note["right"] = self._note_name(midi_note)
        self.notes_played += 1
        
        # Reset activity after duration
        threading.Timer(duration_ms / 1000, self._reset_activity).start()
    
    def _reset_activity(self):
        """Reset channel activity"""
        self.channel_activity["left"] = False
        self.channel_activity["right"] = False
    
    def _note_name(self, midi_note):
        """Convert MIDI note to name"""
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        octave = (midi_note // 12) - 1
        note = notes[midi_note % 12]
        return f"{note}{octave}"
    
    def note_name_to_midi(self, note_name):
        """Convert note name back to MIDI number"""
        notes = {'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4, 'F': 5, 'F#': 6, 'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11}
        if len(note_name) < 2:
            return 60  # Default to C4
        note = note_name[:-1]
        octave = int(note_name[-1])
        return (octave + 1) * 12 + notes.get(note, 0)
    
    def midi_to_frequency(self, midi_note):
        """Convert MIDI note to frequency"""
        return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))
    
    def setup_terminal_input(self):
        """Setup terminal input handling"""
        # Save the terminal settings
        self.old_terminal_settings = termios.tcgetattr(sys.stdin)
        # New terminal setting unbuffered
        tty.setcbreak(sys.stdin.fileno())

    def restore_terminal_input(self):
        """Restore terminal input handling"""
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_terminal_settings)

    def handle_input(self):
        """Handle input from the terminal"""
        if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
            key = sys.stdin.read(1)
            
            # Handle escape sequences (arrow keys)
            if key == '\x1b':  # ESC sequence start
                if self.browsing_files:
                    self.browsing_files = False  # ESC to exit browser
                    return
                # Check if there's more input (arrow keys)
                if select.select([sys.stdin], [], [], 0.1) == ([sys.stdin], [], []):
                    key2 = sys.stdin.read(1)
                    if key2 == '[':
                        if select.select([sys.stdin], [], [], 0.1) == ([sys.stdin], [], []):
                            key3 = sys.stdin.read(1)
                            if self.browsing_files:
                                self.handle_arrow_key(key3)
                            return
                return
            
            if key == 'q':
                self.quit_app()
            elif key == ' ':  # Space
                self.play_demo_note()
            elif key == '1':
                self.play_mono_note(60, 400)
            elif key == '2':
                self.play_mono_note(62, 400)
            elif key == '3':
                self.play_mono_note(64, 400)
            elif key == '4':
                self.play_mono_note(65, 400)
            elif key == '5':
                self.play_mono_note(67, 400)
            elif key == 'c':
                self.play_chord()
            elif key == 'r':
                self.reset_stats()
            elif key == 'm':  # New key for MIDI file browser
                self.show_midi_browser()
            elif key == 's':  # Stop playback
                self.stop_playback()
            elif self.browsing_files:
                self.handle_browser_input(key)
    
    def show_midi_browser(self):
        """Show MIDI file browser"""
        midi_files = self.find_midi_files()
        if not midi_files:
            return
        
        # Set a flag to indicate we're browsing
        self.browsing_files = True
    
    def find_midi_files(self, directory="."):
        """Find MIDI files in directory"""
        midi_extensions = ['.mid', '.midi', '.MID', '.MIDI']
        midi_files = []
        
        path = Path(directory)
        for ext in midi_extensions:
            midi_files.extend(path.glob(f"*{ext}"))
        
        return sorted(midi_files)
    
    def create_midi_browser_panel(self):
        """Create MIDI file browser panel"""
        midi_files = self.find_midi_files()
        if not midi_files:
            return Panel(
                Text("No MIDI files found", style="yellow"),
                title="🎵 MIDI Browser",
                border_style="yellow"
            )
        
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("#", style="bold cyan")
        table.add_column("File", style="white")
        
        for i, midi_file in enumerate(midi_files):
            if i == self.selected_file_index:
                # Highlight selected file
                table.add_row(f">{i+1}", f"[bold green]{midi_file.name}[/bold green]")
            else:
                table.add_row(str(i+1), midi_file.name)
        
        # Add instructions
        table.add_row("", "")
        table.add_row("↑↓", "Navigate")
        table.add_row("Enter", "Play")
        table.add_row("Esc", "Cancel")
        
        return Panel(
            table,
            title="🎵 MIDI Browser (Use ↑↓ Enter Esc)",
            border_style="cyan"
        )
    
    def handle_arrow_key(self, key):
        """Handle arrow key input"""
        midi_files = self.find_midi_files()
        if not midi_files:
            return
            
        if key == 'A':  # Up arrow
            self.selected_file_index = max(0, self.selected_file_index - 1)
        elif key == 'B':  # Down arrow
            self.selected_file_index = min(len(midi_files) - 1, self.selected_file_index + 1)
    
    def handle_browser_input(self, key):
        """Handle input while browsing MIDI files"""
        midi_files = self.find_midi_files()
        if not midi_files:
            self.browsing_files = False
            return
        
        if key == '\r' or key == '\n':  # Enter key
            selected_file = midi_files[self.selected_file_index]
            self.current_file = selected_file.name
            self.browsing_files = False
            # Start MIDI playback in a separate thread
            threading.Thread(target=self.play_midi_file, args=(str(selected_file),), daemon=True).start()
        elif key.isdigit():
            # Direct number selection
            file_idx = int(key) - 1
            if 0 <= file_idx < len(midi_files):
                selected_file = midi_files[file_idx]
                self.current_file = selected_file.name
                self.browsing_files = False
                threading.Thread(target=self.play_midi_file, args=(str(selected_file),), daemon=True).start()
    
    def quit_app(self):
        """Quit the application"""
        self.running = False
    
    def play_demo_note(self):
        """Play a random demo note"""
        note = random.choice([60, 62, 64, 65, 67, 69, 71, 72])
        self.play_mono_note(note, 500)
    
    def play_chord(self):
        """Play a chord"""
        if self.connected:
            self.send_command("CHORD,60,64,800")
            self.channel_activity["left"] = True
            self.channel_activity["right"] = True
            self.last_note["left"] = "C4"
            self.last_note["right"] = "E4"
            self.notes_played += 2
            threading.Timer(0.8, self._reset_activity).start()
    
    def reset_stats(self):
        """Reset statistics"""
        self.notes_played = 0
        self._reset_activity()
    
    def stop_playback(self):
        """Stop MIDI playback"""
        self.playing = False
        if self.connected:
            self.send_command("STOP")
        self._reset_activity()
    
    def run(self):
        """Run the TUI"""
        self.start_time = time.time()
        self.running = True
        
        # Try to connect
        self.connect()
        
        # No need for separate keyboard handlers anymore
        
        try:
            with Live(self.layout, refresh_per_second=4, screen=True) as live:
                self.setup_terminal_input()
                try:
                    while self.running:
                        self.handle_input()  # Handle terminal input dynamically
                        self.update_display()
                        time.sleep(0.1)
                finally:
                    self.restore_terminal_input()
        except KeyboardInterrupt:
            self.running = False

def main():
    """Main function"""
    console = Console()
    
    # Show startup splash
    console.print("\n" * 2)
    console.print("[bold magenta]🎵 Arduino MIDI Synthesizer TUI 🎵[/bold magenta]", justify="center")
    console.print("[dim]Initializing beautiful interface...[/dim]", justify="center")
    time.sleep(1.5)
    
    # Create and run TUI
    try:
        tui = ArduinoSynthTUI()
        tui.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Thanks for using Arduino Synth! 👋[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
    finally:
        # Cleanup
        console.print("[dim]Shutting down...[/dim]")

if __name__ == "__main__":
    main()
