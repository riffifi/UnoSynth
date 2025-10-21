#!/usr/bin/env python3
"""
Arduino MIDI Synthesizer GUI
A comprehensive PyQt5 interface with real-time audio visualization
Uses the stereo MIDI player logic from stereo_midi_player.py
"""

import sys
import os
import time
import threading
import serial
import serial.tools.list_ports
import mido
import numpy as np
import random
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QGridLayout, QPushButton, QLabel, 
                           QComboBox, QSlider, QProgressBar, QListWidget, QListWidgetItem,
                           QTextEdit, QGroupBox, QFileDialog, QMessageBox, QLineEdit,
                           QFrame, QSplitter, QTabWidget, QSpinBox, QCheckBox,
                           QScrollArea, QGraphicsView, QGraphicsScene, QGraphicsItem)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRectF, QPointF, QSize
from PyQt5.QtGui import QFont, QPalette, QColor, QPixmap, QPainter, QBrush, QPen, QLinearGradient, QPolygonF, QRadialGradient
import pyqtgraph as pg

class ArduinoConnection(QThread):
    """Thread for Arduino communication"""
    status_update = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)
    
    def __init__(self, port=None, baud_rate=9600):
        super().__init__()
        self.port = port
        self.baud_rate = baud_rate
        self.arduino = None
        self.connected = False
        self.running = False
        
    @staticmethod
    def get_available_ports():
        """Get list of available serial ports"""
        ports = []
        try:
            available_ports = serial.tools.list_ports.comports()
            for port in available_ports:
                ports.append({
                    'device': port.device,
                    'description': port.description,
                    'hwid': port.hwid
                })
        except Exception as e:
            print(f"Error detecting ports: {e}")
        return ports
    
    @staticmethod
    def get_default_port():
        """Get default port based on operating system"""
        ports = ArduinoConnection.get_available_ports()
        
        # Look for common Arduino ports
        arduino_keywords = ['arduino', 'usb', 'acm', 'usbmodem']
        
        for port in ports:
            device = port['device'].lower()
            description = port['description'].lower()
            
            # Linux: /dev/ttyUSB* or /dev/ttyACM*
            if device.startswith('/dev/ttyusb') or device.startswith('/dev/ttyacm'):
                return port['device']
            
            # macOS: /dev/cu.usbmodem*
            if device.startswith('/dev/cu.usbmodem'):
                return port['device']
            
            # Windows: COM ports
            if device.startswith('com'):
                return port['device']
            
            # Check description for Arduino keywords
            if any(keyword in description for keyword in arduino_keywords):
                return port['device']
        
        # If no Arduino port found, return first available port
        if ports:
            return ports[0]['device']
        
        # Fallback defaults
        if os.name == 'posix':  # Linux/macOS
            return '/dev/ttyUSB0'
        else:  # Windows
            return 'COM3'
        
    def connect_arduino(self):
        """Connect to Arduino"""
        try:
            self.arduino = serial.Serial(self.port, self.baud_rate, timeout=1)
            time.sleep(2)  # Wait for Arduino initialization
            self.connected = True
            self.status_update.emit(f"Connected to Arduino on {self.port}")
            self.connection_changed.emit(True)
            return True
        except serial.SerialException as e:
            self.status_update.emit(f"Failed to connect: {str(e)}")
            self.connection_changed.emit(False)
            return False
    
    def disconnect_arduino(self):
        """Disconnect from Arduino"""
        if self.arduino and self.connected:
            self.send_command("STOP")
            self.arduino.close()
            self.connected = False
            self.status_update.emit("Disconnected from Arduino")
            self.connection_changed.emit(False)
    
    def send_command(self, command):
        """Send command to Arduino"""
        if not self.connected or not self.arduino:
            return False
        try:
            self.arduino.write(f"{command}\n".encode())
            return True
        except serial.SerialException as e:
            self.status_update.emit(f"Error sending command: {str(e)}")
            return False

class PianoRollWidget(QWidget):
    """Professional DAW-style piano roll widget with piano keys and note blocks"""
    
    def __init__(self):
        super().__init__()
        self.zoom_level = 1.0  # 1.0 = normal, 2.0 = zoomed in 2x, 0.5 = zoomed out 2x
        self.vertical_zoom = 1.0  # Vertical zoom level
        self.setup_ui()
        self.setup_data()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        
        # Top toolbar with zoom controls
        toolbar = self.create_toolbar()
        layout.addWidget(toolbar)
        
        # Create scroll area for vertical scrolling
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        
        # Container widget for piano roll content
        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Piano keys widget (left side)
        self.piano_keys = PianoKeysWidget()
        self.piano_keys.setFixedWidth(80)
        container_layout.addWidget(self.piano_keys)
        
        # Note area widget (right side)
        self.note_area = NoteAreaWidget()
        container_layout.addWidget(self.note_area)
        
        # Set fixed height for 109 keys (MIDI 0-108)
        total_height = 109 * 15  # 15 pixels per key
        container.setMinimumHeight(total_height)
        self.piano_keys.setMinimumHeight(total_height)
        self.note_area.setMinimumHeight(total_height)
        
        # Add container to scroll area
        scroll_area.setWidget(container)
        
        # Store scroll area reference for programmatic scrolling
        self.scroll_area = scroll_area
        
        # Connect vertical scrollbar to sync piano keys and note area
        scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)
        
        layout.addWidget(scroll_area)
    
    def create_toolbar(self):
        """Create toolbar with zoom and view controls"""
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: #1a1a1a; padding: 5px;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(5, 2, 5, 2)
        
        # Horizontal zoom controls
        hz_label = QLabel("H-Zoom:")
        hz_label.setStyleSheet("color: #ffffff; font-weight: bold;")
        toolbar_layout.addWidget(hz_label)
        
        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFixedSize(30, 25)
        zoom_out_btn.clicked.connect(self.zoom_out_horizontal)
        toolbar_layout.addWidget(zoom_out_btn)
        
        self.zoom_label = QLabel("1.0x")
        self.zoom_label.setStyleSheet("color: #00ff00; font-weight: bold; min-width: 50px;")
        self.zoom_label.setAlignment(Qt.AlignCenter)
        toolbar_layout.addWidget(self.zoom_label)
        
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedSize(30, 25)
        zoom_in_btn.clicked.connect(self.zoom_in_horizontal)
        toolbar_layout.addWidget(zoom_in_btn)
        
        zoom_reset_btn = QPushButton("Reset")
        zoom_reset_btn.setFixedWidth(50)
        zoom_reset_btn.clicked.connect(self.zoom_reset)
        toolbar_layout.addWidget(zoom_reset_btn)
        
        toolbar_layout.addSpacing(20)
        
        # Vertical zoom controls
        vz_label = QLabel("V-Zoom:")
        vz_label.setStyleSheet("color: #ffffff; font-weight: bold;")
        toolbar_layout.addWidget(vz_label)
        
        vzoom_out_btn = QPushButton("−")
        vzoom_out_btn.setFixedSize(30, 25)
        vzoom_out_btn.clicked.connect(self.zoom_out_vertical)
        toolbar_layout.addWidget(vzoom_out_btn)
        
        self.vzoom_label = QLabel("1.0x")
        self.vzoom_label.setStyleSheet("color: #00ff00; font-weight: bold; min-width: 50px;")
        self.vzoom_label.setAlignment(Qt.AlignCenter)
        toolbar_layout.addWidget(self.vzoom_label)
        
        vzoom_in_btn = QPushButton("+")
        vzoom_in_btn.setFixedSize(30, 25)
        vzoom_in_btn.clicked.connect(self.zoom_in_vertical)
        toolbar_layout.addWidget(vzoom_in_btn)
        
        toolbar_layout.addStretch()
        
        # Info label
        self.info_label = QLabel("Notes: 0 | Range: 10s")
        self.info_label.setStyleSheet("color: #888888; font-size: 11px;")
        toolbar_layout.addWidget(self.info_label)
        
        return toolbar
    
    def zoom_in_horizontal(self):
        """Zoom in horizontally (show less time, more detail)"""
        self.zoom_level = min(4.0, self.zoom_level * 1.5)
        self.update_zoom()
    
    def zoom_out_horizontal(self):
        """Zoom out horizontally (show more time, less detail)"""
        self.zoom_level = max(0.25, self.zoom_level / 1.5)
        self.update_zoom()
    
    def zoom_in_vertical(self):
        """Zoom in vertically (larger keys)"""
        self.vertical_zoom = min(3.0, self.vertical_zoom * 1.5)
        self.update_vertical_zoom()
    
    def zoom_out_vertical(self):
        """Zoom out vertically (smaller keys)"""
        self.vertical_zoom = max(0.5, self.vertical_zoom / 1.5)
        self.update_vertical_zoom()
    
    def zoom_reset(self):
        """Reset all zoom levels"""
        self.zoom_level = 1.0
        self.vertical_zoom = 1.0
        self.update_zoom()
        self.update_vertical_zoom()
    
    def update_zoom(self):
        """Update horizontal zoom"""
        base_time_range = 10.0
        self.time_range = base_time_range / self.zoom_level
        self.note_area.time_range = self.time_range
        self.zoom_label.setText(f"{self.zoom_level:.1f}x")
        self.info_label.setText(f"Notes: {len(self.notes)} | Range: {self.time_range:.1f}s")
        self.note_area.update()
    
    def update_vertical_zoom(self):
        """Update vertical zoom"""
        base_key_height = 15
        new_key_height = int(base_key_height * self.vertical_zoom)
        self.piano_keys.key_height = new_key_height
        self.note_area.key_height = new_key_height
        
        # Update heights
        total_height = 109 * new_key_height
        self.piano_keys.setMinimumHeight(total_height)
        self.note_area.setMinimumHeight(total_height)
        
        self.vzoom_label.setText(f"{self.vertical_zoom:.1f}x")
        self.piano_keys.update()
        self.note_area.update()
        
    def _on_scroll(self, value):
        """Handle scroll events to keep piano keys and notes in sync"""
        self.note_area.scroll_position = value
        self.piano_keys.scroll_position = value
        self.update()
        
    def setup_data(self):
        """Initialize piano roll data"""
        self.notes = []  # List of note dictionaries
        self.current_time = 0
        self.playback_start_time = None  # Track when playback started
        self.time_range = 10  # 10 seconds visible at a time
        self.time_offset = None  # Current horizontal scroll offset (absolute time)
        
    def add_note(self, midi_note, channel, start_time, duration):
        """Add a note to the piano roll"""
        note = {
            'midi_note': midi_note,
            'channel': channel,
            'start_time': start_time,
            'duration': duration,
            'end_time': start_time + duration
        }
        self.notes.append(note)
        
        # Initialize playback start time and time offset on first note
        if self.playback_start_time is None:
            self.playback_start_time = start_time
            self.time_offset = start_time  # Start viewing from the beginning
            self.note_area.time_offset = self.time_offset
            print(f"Piano Roll: First note at {start_time:.2f}, MIDI={midi_note}, channel={channel}")
        
        # Update note area
        self.note_area.add_note(note)
        
        # Auto-scroll horizontally during playback
        self._auto_scroll_horizontal(start_time)
        
        # Keep only notes in recent time window
        cutoff_time = start_time - 300  # Keep last 5 minutes
        self.notes = [note for note in self.notes if note['end_time'] > cutoff_time]
        self.note_area.notes = [note for note in self.note_area.notes if note['end_time'] > cutoff_time]
        
        # Update info label
        if hasattr(self, 'info_label'):
            self.info_label.setText(f"Notes: {len(self.notes)} | Range: {self.time_range:.1f}s")
        
    def _auto_scroll_horizontal(self, current_time):
        """Auto-scroll horizontally to follow playback"""
        if self.playback_start_time is None:
            return
        
        # Calculate time offset to keep current time at 20% from left edge
        # Use playback_start_time as the base for relative time calculations
        elapsed = current_time - self.playback_start_time
        self.time_offset = self.playback_start_time + max(0, elapsed - self.time_range * 0.2)
        
        # Update note area with new time window
        self.note_area.time_offset = self.time_offset
        self.note_area.update()
        
    def update_time(self, current_time):
        """Update current playback time"""
        self.current_time = current_time
        self.note_area.set_current_time(current_time)

class PianoKeysWidget(QWidget):
    """Piano keys widget showing the keyboard"""
    scroll_changed = pyqtSignal(int)
    
    def __init__(self):
        super().__init__()
        self.setFixedWidth(80)
        self.setMinimumHeight(109 * 15)  # 109 keys * 15 pixels
        self.scroll_position = 0
        self.key_height = 15  # Consistent height for all keys
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Background
        painter.fillRect(self.rect(), QColor(40, 40, 40))
        
        # Draw piano keys
        self.draw_piano_keys(painter)
        
    def draw_piano_keys(self, painter):
        """Draw piano keys"""
        # Start from C8 (MIDI 108) and go down
        start_note = 108
        y_pos = 0
        
        for i in range(108, -1, -1):  # From C8 down to C-1
            midi_note = i
            octave = (midi_note // 12) - 1
            note_in_octave = midi_note % 12
            
            # Determine if it's a black or white key
            is_black = note_in_octave in [1, 3, 6, 8, 10]  # C#, D#, F#, G#, A#
            
            if is_black:
                # Black key
                painter.fillRect(0, y_pos, 50, self.key_height, QColor(20, 20, 20))
                painter.setPen(QPen(QColor(60, 60, 60), 1))
                painter.drawRect(0, y_pos, 50, self.key_height)
            else:
                # White key
                painter.fillRect(0, y_pos, 80, self.key_height, QColor(250, 250, 250))
                painter.setPen(QPen(QColor(200, 200, 200), 1))
                painter.drawRect(0, y_pos, 80, self.key_height)
                
                # Add note name for important notes
                if note_in_octave in [0, 4, 7]:  # C, E, G
                    note_names = ['C', 'D', 'E', 'F', 'G', 'A', 'B']
                    note_name = note_names[note_in_octave // 2] if note_in_octave < 7 else note_names[note_in_octave - 7]
                    painter.setPen(QPen(QColor(100, 100, 100), 1))
                    painter.setFont(QFont("Arial", 8))
                    painter.drawText(5, y_pos + 15, f"{note_name}{octave}")
            
            y_pos += self.key_height
            
            # Draw black keys on top of white keys
            if is_black:
                painter.fillRect(50, y_pos - self.key_height, 30, self.key_height, QColor(20, 20, 20))
                painter.setPen(QPen(QColor(60, 60, 60), 1))
                painter.drawRect(50, y_pos - self.key_height, 30, self.key_height)

class NoteAreaWidget(QWidget):
    """Note area widget showing note blocks"""
    
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(109 * 15)  # 109 keys * 15 pixels
        self.notes = []
        self.current_time = 0
        self.time_range = 10  # 10 seconds visible at a time
        self.time_offset = None  # Horizontal scroll offset (absolute time)
        self.scroll_position = 0
        self.key_height = 15  # Consistent height for all keys
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Background
        painter.fillRect(self.rect(), QColor(30, 30, 30))
        
        # Draw grid lines
        self.draw_grid(painter)
        
        # Draw notes
        self.draw_notes(painter)
        
        # Draw current time line
        self.draw_current_time_line(painter)
        
    def draw_grid(self, painter):
        """Draw professional DAW-style grid"""
        # Draw horizontal lines with alternating shades for white/black keys
        for i in range(109):
            y = i * self.key_height
            midi_note = 108 - i
            note_in_octave = midi_note % 12
            is_black = note_in_octave in [1, 3, 6, 8, 10]
            
            # Alternate background colors for easier reading
            if is_black:
                painter.fillRect(0, y, self.width(), self.key_height, QColor(25, 25, 25))
            
            # Draw octave separators (C notes) brighter
            if note_in_octave == 0:
                painter.setPen(QPen(QColor(100, 100, 100), 1))
            else:
                painter.setPen(QPen(QColor(40, 40, 40), 1))
            painter.drawLine(0, y, self.width(), y)
        
        # Vertical lines (time separators) - adaptive based on zoom
        if self.time_range > 20:
            time_step = 5.0  # 5 second intervals when zoomed out
            beat_interval = 20
        elif self.time_range > 10:
            time_step = 2.0  # 2 second intervals
            beat_interval = 8
        elif self.time_range > 5:
            time_step = 1.0  # 1 second intervals
            beat_interval = 4
        else:
            time_step = 0.5  # 0.5 second intervals when zoomed in
            beat_interval = 2
        
        num_lines = int(self.time_range / time_step) + 1
        for i in range(num_lines):
            x = int((i * time_step / self.time_range) * self.width())
            # Draw measure lines (every 4 beats) brighter
            if i % beat_interval == 0:
                painter.setPen(QPen(QColor(90, 90, 90), 2))
            elif i % (beat_interval // 2) == 0:
                painter.setPen(QPen(QColor(70, 70, 70), 1))
            else:
                painter.setPen(QPen(QColor(50, 50, 50), 1))
            painter.drawLine(x, 0, x, self.height())
            
    def draw_notes(self, painter):
        """Draw note blocks"""
        widget_width = self.width()
        widget_height = self.height()
        
        # Skip drawing if time_offset not initialized
        if self.time_offset is None:
            return
        
        # Debug: print number of notes
        if len(self.notes) > 0 and len(self.notes) % 10 == 1:
            print(f"Drawing {len(self.notes)} notes, time_offset={self.time_offset:.2f}, time_range={self.time_range}")
        
        for note in self.notes:
            # Calculate position
            midi_note = max(0, min(108, note['midi_note']))  # Clamp MIDI note range
            y = (108 - midi_note) * self.key_height
            
            # Calculate x position relative to time window with overflow protection
            relative_start = note['start_time'] - self.time_offset
            start_x_float = (relative_start / self.time_range) * widget_width
            width_float = (note['duration'] / self.time_range) * widget_width
            
            # Clamp to valid int32 range and viewport
            start_x = max(-2147483648, min(2147483647, int(start_x_float)))
            width = max(1, min(2147483647, int(width_float)))
            
            # Skip notes that are completely outside the visible time window
            if start_x + width < -100 or start_x > widget_width + 100:
                continue
            
            # Skip notes that are outside vertical bounds
            if y < 0 or y > widget_height:
                continue
            
            # Clamp drawing coordinates to visible area
            if start_x < -10000:
                width = max(0, width + start_x + 10000)
                start_x = -10000
            if start_x + width > widget_width + 10000:
                width = widget_width + 10000 - start_x
            
            # Skip if width is too small after clamping
            if width <= 0:
                continue
            
            # Choose color based on channel with professional gradients
            if note['channel'] == 'left':
                base_color = QColor(50, 150, 255)  # Blue for left channel
                highlight_color = QColor(80, 180, 255)
            else:
                base_color = QColor(255, 80, 150)  # Pink for right channel
                highlight_color = QColor(255, 120, 180)
            
            # Draw note block with gradient and 3D effect
            from PyQt5.QtGui import QLinearGradient
            gradient = QLinearGradient(start_x, y, start_x, y + self.key_height - 1)
            gradient.setColorAt(0, highlight_color)
            gradient.setColorAt(0.5, base_color)
            gradient.setColorAt(1, base_color.darker(120))
            
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(gradient))
            painter.drawRoundedRect(start_x, y, width, self.key_height - 1, 3, 3)
            
            # Draw top highlight for 3D effect
            painter.setPen(QPen(QColor(255, 255, 255, 80), 1))
            painter.drawLine(start_x + 2, y + 1, start_x + width - 2, y + 1)
            
            # Draw outline
            painter.setPen(QPen(base_color.lighter(140), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(start_x, y, width, self.key_height - 1, 3, 3)
            
            # Add velocity indicator (small bar on left side)
            vel_width = max(2, int(width * 0.15))
            painter.fillRect(start_x, y, vel_width, self.key_height - 1, 
                           QColor(255, 255, 255, 100))
            
    def draw_current_time_line(self, painter):
        """Draw current playback time line"""
        if self.current_time > 0 and self.time_offset is not None:
            # Calculate x position relative to time window
            relative_time = self.current_time - self.time_offset
            x_float = (relative_time / self.time_range) * self.width()
            # Clamp to valid int32 range to prevent overflow
            x = max(-2147483648, min(2147483647, int(x_float)))
            # Only draw if within visible range
            if 0 <= x <= self.width():
                # Draw playhead with glow effect
                from PyQt5.QtGui import QRadialGradient
                
                # Glow effect
                for offset in range(3, 0, -1):
                    alpha = 50 * (4 - offset)
                    painter.setPen(QPen(QColor(255, 255, 0, alpha), offset * 2))
                    painter.drawLine(x, 0, x, self.height())
                
                # Main playhead line
                painter.setPen(QPen(QColor(255, 255, 255, 255), 2))
                painter.drawLine(x, 0, x, self.height())
                
                # Draw playhead indicator at top
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(255, 255, 255, 255)))
                # Triangle
                from PyQt5.QtGui import QPolygonF
                points = QPolygonF([
                    QPointF(x, 0),
                    QPointF(x - 8, 15),
                    QPointF(x + 8, 15)
                ])
                painter.drawPolygon(points)
                
                # Inner triangle for contrast
                painter.setBrush(QBrush(QColor(255, 255, 0, 255)))
                inner_points = QPolygonF([
                    QPointF(x, 3),
                    QPointF(x - 6, 13),
                    QPointF(x + 6, 13)
                ])
                painter.drawPolygon(inner_points)
            
    def add_note(self, note):
        """Add a note to the display"""
        self.notes.append(note)
        self.update()
        
    def set_current_time(self, current_time):
        """Set current playback time"""
        self.current_time = current_time
        self.update()
        
    def set_scroll_position(self, position):
        """Set scroll position"""
        self.scroll_position = position
        self.update()

class AudioVisualizer(QWidget):
    """Arduino synthesizer visualizer widget"""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_synth_data()
        
        # Current playing state
        self.left_channel = {'active': False, 'frequency': 0, 'note': '---', 'start_time': 0}
        self.right_channel = {'active': False, 'frequency': 0, 'note': '---', 'start_time': 0}
        self.note_history = []
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Stereo channel visualization
        channels_widget = QWidget()
        channels_layout = QHBoxLayout(channels_widget)
        
        # Left channel
        left_group = QGroupBox("LEFT CHANNEL")
        left_layout = QVBoxLayout(left_group)
        
        self.left_status = QLabel("IDLE")
        self.left_status.setAlignment(Qt.AlignCenter)
        self.left_status.setStyleSheet("color: #ff6666; font-weight: bold; font-size: 14px;")
        left_layout.addWidget(self.left_status)
        
        self.left_note = QLabel("---")
        self.left_note.setAlignment(Qt.AlignCenter)
        self.left_note.setFont(QFont("Arial", 18, QFont.Bold))
        left_layout.addWidget(self.left_note)
        
        self.left_freq = QLabel("--- Hz")
        self.left_freq.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.left_freq)
        
        channels_layout.addWidget(left_group)
        
        # Right channel
        right_group = QGroupBox("RIGHT CHANNEL")
        right_layout = QVBoxLayout(right_group)
        
        self.right_status = QLabel("IDLE")
        self.right_status.setAlignment(Qt.AlignCenter)
        self.right_status.setStyleSheet("color: #ff6666; font-weight: bold; font-size: 14px;")
        right_layout.addWidget(self.right_status)
        
        self.right_note = QLabel("---")
        self.right_note.setAlignment(Qt.AlignCenter)
        self.right_note.setFont(QFont("Arial", 18, QFont.Bold))
        right_layout.addWidget(self.right_note)
        
        self.right_freq = QLabel("--- Hz")
        self.right_freq.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.right_freq)
        
        channels_layout.addWidget(right_group)
        layout.addWidget(channels_widget)
        
        # Tabbed visualization area
        viz_tabs = QTabWidget()
        
        # Tab 1: Enhanced frequency spectrum with musical note markers
        spectrum_widget = QWidget()
        spectrum_layout = QVBoxLayout(spectrum_widget)
        
        self.spectrum_plot = pg.PlotWidget(title="Musical Frequency Spectrum")
        self.spectrum_plot.setLabel('left', 'Amplitude')
        self.spectrum_plot.setLabel('bottom', 'Frequency (Hz)')
        self.spectrum_plot.setXRange(0, 4000)  # Extended range for high notes
        self.spectrum_plot.setYRange(0, 1)
        
        # Add musical note frequency markers
        self.add_musical_note_markers()
        
        # Create frequency markers for both channels
        self.left_freq_line = pg.InfiniteLine(angle=90, pen=pg.mkPen('cyan', width=3))
        self.right_freq_line = pg.InfiniteLine(angle=90, pen=pg.mkPen('magenta', width=3))
        self.spectrum_plot.addItem(self.left_freq_line)
        self.spectrum_plot.addItem(self.right_freq_line)
        
        # Add frequency spectrum curve
        self.spectrum_curve = self.spectrum_plot.plot(pen=pg.mkPen('white', width=2), name='Spectrum')
        
        spectrum_layout.addWidget(self.spectrum_plot)
        viz_tabs.addTab(spectrum_widget, "Musical Spectrum")
        
        # Tab 2: Oscilloscope (ECG-style waveform)
        osc_widget = QWidget()
        osc_layout = QVBoxLayout(osc_widget)
        
        self.oscilloscope_plot = pg.PlotWidget(title="Oscilloscope - Synthesized Waveform")
        self.oscilloscope_plot.setLabel('left', 'Amplitude')
        self.oscilloscope_plot.setLabel('bottom', 'Time (ms)')
        self.oscilloscope_plot.setYRange(-1, 1)
        self.oscilloscope_plot.setXRange(0, 100)  # 100ms window
        
        # Waveform curves for left and right channels
        self.left_waveform = self.oscilloscope_plot.plot(pen=pg.mkPen('cyan', width=2), name='Left Channel')
        self.right_waveform = self.oscilloscope_plot.plot(pen=pg.mkPen('magenta', width=2), name='Right Channel')
        
        # Add legend
        self.oscilloscope_plot.addLegend()
        
        osc_layout.addWidget(self.oscilloscope_plot)
        viz_tabs.addTab(osc_widget, "Oscilloscope")
        
        # Tab 3: Spectrogram (frequency over time)
        spectrogram_widget = QWidget()
        spectrogram_layout = QVBoxLayout(spectrogram_widget)
        
        self.spectrogram_plot = pg.PlotWidget(title="Spectrogram - Frequency vs Time")
        self.spectrogram_plot.setLabel('left', 'Frequency (Hz)')
        self.spectrogram_plot.setLabel('bottom', 'Time (s)')
        
        # Create image item for spectrogram
        self.spectrogram_img = pg.ImageItem()
        self.spectrogram_plot.addItem(self.spectrogram_img)
        
        # Color map for spectrogram
        colormap = pg.colormap.get('viridis')
        self.spectrogram_img.setColorMap(colormap)
        
        # Initialize spectrogram data buffer
        self.spectrogram_data = np.zeros((100, 50))  # 100 freq bins, 50 time steps
        self.spectrogram_time_idx = 0
        
        spectrogram_layout.addWidget(self.spectrogram_plot)
        viz_tabs.addTab(spectrogram_widget, "Spectrogram")
        
        # Tab 4: Beautiful Piano Roll Visualization
        self.piano_roll_widget = PianoRollWidget()
        viz_tabs.addTab(self.piano_roll_widget, "Piano Roll")
        
        layout.addWidget(viz_tabs)
        
        # Note history log
        history_group = QGroupBox("Note History")
        history_layout = QVBoxLayout(history_group)
        
        self.note_log = QTextEdit()
        self.note_log.setMaximumHeight(150)
        self.note_log.setReadOnly(True)
        self.note_log.setStyleSheet("background-color: #1a1a1a; color: #ffffff; font-family: monospace;")
        history_layout.addWidget(self.note_log)
        
        layout.addWidget(history_group)
        
    def setup_synth_data(self):
        """Setup synthesizer data tracking"""
        # Timer for updating visualization
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_visualization)
        self.timer.start(100)  # Update every 100ms
        
        # Initialize frequency lines as hidden
        self.left_freq_line.hide()
        self.right_freq_line.hide()
    
    def add_musical_note_markers(self):
        """Add vertical lines for musical note frequencies"""
        # Add markers for each octave from C0 to C8
        for octave in range(9):  # C0 to C8
            for note_idx, note_name in enumerate(['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']):
                midi_note = octave * 12 + note_idx
                frequency = 440.0 * (2.0 ** ((midi_note - 69) / 12.0))
                
                if frequency <= 4000:  # Only show notes within our range
                    # Different colors for different octaves
                    colors = ['#ff6666', '#ffaa66', '#ffff66', '#aaff66', '#66ff66', 
                             '#66ffaa', '#66ffff', '#66aaff', '#6666ff']
                    color = colors[octave % len(colors)]
                    
                    # Add vertical line
                    line = pg.InfiniteLine(pos=frequency, angle=90, 
                                        pen=pg.mkPen(color, width=1, style=Qt.DashLine))
                    self.spectrum_plot.addItem(line)
                    
                    # Add note label for important notes (C, E, G)
                    if note_name in ['C', 'E', 'G']:
                        text = pg.TextItem(f"{note_name}{octave}", color=color, anchor=(0.5, 1))
                        text.setPos(frequency, 0.9)
                        self.spectrum_plot.addItem(text)
    
    def update_visualization(self):
        """Update synthesizer visualization"""
        current_time = time.time()
        
        # Check if channels should be marked as inactive
        if self.left_channel['active'] and current_time - self.left_channel['start_time'] > 2.0:
            self.set_channel_inactive('left')
            
        if self.right_channel['active'] and current_time - self.right_channel['start_time'] > 2.0:
            self.set_channel_inactive('right')
        
        # Update all visualizations
        self.update_oscilloscope()
        self.update_spectrogram()
        self.update_spectrum()
        
        # Update piano roll current time
        if hasattr(self, 'piano_roll_widget'):
            self.piano_roll_widget.update_time(current_time)
    
    def play_note_on_channel(self, channel, note_name, frequency, duration_ms):
        """Update visualization when a note is played on a specific channel"""
        current_time = time.time()
        
        if channel == 'left':
            self.left_channel = {
                'active': True,
                'frequency': frequency,
                'note': note_name,
                'start_time': current_time
            }
            self.left_status.setText("PLAYING")
            self.left_status.setStyleSheet("color: #00ff00; font-weight: bold; font-size: 14px;")
            self.left_note.setText(note_name)
            self.left_freq.setText(f"{frequency:.1f} Hz")
            self.left_freq_line.setPos(frequency)
            self.left_freq_line.show()
            
        elif channel == 'right':
            self.right_channel = {
                'active': True,
                'frequency': frequency,
                'note': note_name,
                'start_time': current_time
            }
            self.right_status.setText("PLAYING")
            self.right_status.setStyleSheet("color: #00ff00; font-weight: bold; font-size: 14px;")
            self.right_note.setText(note_name)
            self.right_freq.setText(f"{frequency:.1f} Hz")
            self.right_freq_line.setPos(frequency)
            self.right_freq_line.show()
        
        # Update oscilloscope and spectrogram
        self.update_oscilloscope()
        self.update_spectrogram()
        
        # Add to piano roll (convert note name to MIDI number)
        midi_note = self.note_name_to_midi(note_name)
        if midi_note is not None and hasattr(self, 'piano_roll_widget'):
            current_time = time.time()
            self.piano_roll_widget.add_note(midi_note, channel, current_time, duration_ms / 1000.0)
        
        # Log the note
        self.log_note(channel, note_name, frequency, duration_ms)
    
    def play_mono_note(self, note_name, frequency, duration_ms):
        """Play note on both channels (mono mode)"""
        self.play_note_on_channel('left', note_name, frequency, duration_ms)
        self.play_note_on_channel('right', note_name, frequency, duration_ms)
    
    def play_chord_notes(self, left_note, left_freq, right_note, right_freq, duration_ms):
        """Play different notes on left and right channels (chord mode)"""
        self.play_note_on_channel('left', left_note, left_freq, duration_ms)
        self.play_note_on_channel('right', right_note, right_freq, duration_ms)
    
    def set_channel_inactive(self, channel):
        """Mark a channel as inactive"""
        if channel == 'left':
            self.left_channel['active'] = False
            self.left_status.setText("IDLE")
            self.left_status.setStyleSheet("color: #ff6666; font-weight: bold; font-size: 14px;")
            self.left_note.setText("---")
            self.left_freq.setText("--- Hz")
            self.left_freq_line.hide()
            
        elif channel == 'right':
            self.right_channel['active'] = False
            self.right_status.setText("IDLE")
            self.right_status.setStyleSheet("color: #ff6666; font-weight: bold; font-size: 14px;")
            self.right_note.setText("---")
            self.right_freq.setText("--- Hz")
            self.right_freq_line.hide()
    
    def log_note(self, channel, note_name, frequency, duration_ms):
        """Log a played note to the history"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {channel.upper()}: {note_name} ({frequency:.1f}Hz) - {duration_ms}ms"
        
        self.note_history.append(log_entry)
        
        # Keep only last 50 entries
        if len(self.note_history) > 50:
            self.note_history = self.note_history[-50:]
        
        # Update the log display
        self.note_log.setPlainText('\n'.join(self.note_history))
        
        # Scroll to bottom
        cursor = self.note_log.textCursor()
        cursor.movePosition(cursor.End)
        self.note_log.setTextCursor(cursor)
    
    def update_oscilloscope(self):
        """Generate and display synthesized waveforms"""
        # Generate time array for 100ms window
        sample_rate = 44100
        duration = 0.1  # 100ms
        t = np.linspace(0, duration, int(sample_rate * duration))
        time_ms = t * 1000  # Convert to milliseconds
        
        # Generate left channel waveform
        if self.left_channel['active']:
            left_freq = self.left_channel['frequency']
            left_wave = np.sin(2 * np.pi * left_freq * t) * 0.8
        else:
            left_wave = np.zeros_like(t)
        
        # Generate right channel waveform
        if self.right_channel['active']:
            right_freq = self.right_channel['frequency']
            right_wave = np.sin(2 * np.pi * right_freq * t) * 0.8
        else:
            right_wave = np.zeros_like(t)
        
        # Update oscilloscope plots
        self.left_waveform.setData(time_ms, left_wave)
        self.right_waveform.setData(time_ms, right_wave)
    
    def update_spectrogram(self):
        """Update spectrogram with current frequency content"""
        # Create frequency bins
        freq_bins = np.linspace(0, 2000, 100)  # 0-2000 Hz, 100 bins
        
        # Create current frequency spectrum
        current_spectrum = np.zeros(100)
        
        # Add peaks for active frequencies
        if self.left_channel['active']:
            freq = self.left_channel['frequency']
            if freq <= 2000:
                bin_idx = int((freq / 2000) * 99)
                current_spectrum[bin_idx] = 1.0
        
        if self.right_channel['active']:
            freq = self.right_channel['frequency']
            if freq <= 2000:
                bin_idx = int((freq / 2000) * 99)
                current_spectrum[bin_idx] = max(current_spectrum[bin_idx], 0.8)
        
        # Shift spectrogram data and add new column
        self.spectrogram_data = np.roll(self.spectrogram_data, -1, axis=1)
        self.spectrogram_data[:, -1] = current_spectrum
        
        # Update spectrogram image
        self.spectrogram_img.setImage(self.spectrogram_data, 
                                    pos=[0, 0], 
                                    scale=[1, 2000/100])  # Scale to frequency range
    
    def update_spectrum(self):
        """Update frequency spectrum with current notes"""
        # Create frequency bins
        freq_bins = np.linspace(0, 4000, 200)  # Extended range
        spectrum = np.zeros(200)
        
        # Add peaks for active frequencies
        if self.left_channel['active']:
            freq = self.left_channel['frequency']
            if freq <= 4000:
                bin_idx = int((freq / 4000) * 199)
                spectrum[bin_idx] = 1.0
        
        if self.right_channel['active']:
            freq = self.right_channel['frequency']
            if freq <= 4000:
                bin_idx = int((freq / 4000) * 199)
                spectrum[bin_idx] = max(spectrum[bin_idx], 0.8)
        
        # Update spectrum curve
        self.spectrum_curve.setData(freq_bins, spectrum)
    
    def note_name_to_midi(self, note_name):
        """Convert note name (e.g., 'C4', 'F#5') to MIDI note number"""
        try:
            # Parse note name
            if len(note_name) >= 2:
                note_part = note_name[:-1]  # Everything except last character
                octave = int(note_name[-1])  # Last character is octave
                
                # Note mapping
                note_map = {'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4, 'F': 5, 
                           'F#': 6, 'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11}
                
                if note_part in note_map:
                    midi_note = (octave + 1) * 12 + note_map[note_part]
                    return midi_note
        except (ValueError, KeyError):
            pass
        return None
    
    def stop_all_notes(self):
        """Stop all notes on both channels"""
        self.set_channel_inactive('left')
        self.set_channel_inactive('right')
        # Clear oscilloscope
        self.update_oscilloscope()
        self.update_spectrogram()

class ArduinoStereoMidiPlayer(QThread):
    """Stereo MIDI file player thread - using logic from stereo_midi_player.py"""
    progress_update = pyqtSignal(int)
    status_update = pyqtSignal(str)
    note_played = pyqtSignal(str, float, int)  # note_name, frequency, duration
    chord_played = pyqtSignal(str, float, str, float, int)  # left_note, left_freq, right_note, right_freq, duration
    
    def __init__(self, arduino_connection, stereo_mode="auto", bass_threshold=60):
        super().__init__()
        self.arduino = arduino_connection
        self.current_file = None
        self.playing = False
        self.tempo_multiplier = 1.0
        self.visualizer = None
        self.stereo_mode = stereo_mode
        self.bass_threshold = bass_threshold
        # Track active notes for pitch bend
        self.active_notes = {0: None, 1: None}  # channel: (midi_note, start_time)
        self.pitch_bend_range = 2  # Default pitch bend range in semitones
        
    def load_file(self, file_path):
        """Load MIDI file"""
        self.current_file = file_path
        
    def set_tempo(self, multiplier):
        """Set tempo multiplier"""
        self.tempo_multiplier = multiplier
        
    def set_stereo_mode(self, mode):
        """Set stereo mode"""
        self.stereo_mode = mode
        
    def set_bass_threshold(self, threshold):
        """Set bass threshold"""
        self.bass_threshold = threshold
        
    def play(self):
        """Start playing"""
        if self.current_file and not self.playing:
            self.playing = True
            self.start()
    
    def stop(self):
        """Stop playing"""
        self.playing = False
        if self.arduino.connected:
            self.arduino.send_command("STOP")
        self.status_update.emit("Playback stopped")
        
    def run(self):
        """Play MIDI file using stereo logic"""
        if not self.current_file:
            return
            
        try:
            midi_file = mido.MidiFile(self.current_file)
        except Exception as e:
            self.status_update.emit(f"Error loading MIDI file: {e}")
            return
        
        # Use the stereo player logic
        self._play_stereo_once(midi_file, self.tempo_multiplier, self.stereo_mode, self.bass_threshold)
    
    def _play_stereo_once(self, midi_file, tempo_multiplier, stereo_mode, bass_threshold):
        """Play MIDI file once with stereo processing - from stereo_midi_player.py"""
        notes = self._extract_notes(midi_file)
        stereo_notes = self._assign_stereo_channels(notes, stereo_mode, bass_threshold)
        
        self.status_update.emit(f"Playing {len(stereo_notes)} stereo events...")
        
        # Play the stereo notes
        start_time = time.time()
        
        for i, (note_time, events) in enumerate(stereo_notes):
            if not self.playing:
                break
                
            # Wait until it's time for this event
            target_time = note_time / tempo_multiplier
            current_time = time.time() - start_time
            
            if target_time > current_time:
                time.sleep(target_time - current_time)
            
            # Process all events at this time point
            for event in events:
                if not self.playing:
                    break
                    
                event_type = event['type']
                
                if event_type == 'note':
                    note = event['note']
                    duration = event['duration']
                    channel = event['channel']
                    velocity = event.get('velocity', 100)  # Default to forte if not specified
                    self.play_note_on_channel(note, duration, channel, velocity)

                    # Emit signal for GUI updates
                    note_name = self.midi_to_note_name(note)
                    frequency = self.midi_to_frequency(note)
                    self.note_played.emit(note_name, frequency, duration)

                elif event_type == 'chord':
                    note1 = event['note1']
                    note2 = event['note2']
                    duration = event['duration']
                    vel1 = event.get('vel1', 100)
                    vel2 = event.get('vel2', 100)
                    self.play_chord(note1, note2, duration, vel1, vel2)

                    # Emit signals for chord visualization
                    left_note_name = self.midi_to_note_name(note1)
                    left_freq = self.midi_to_frequency(note1)
                    right_note_name = self.midi_to_note_name(note2)
                    right_freq = self.midi_to_frequency(note2)
                    self.chord_played.emit(left_note_name, left_freq, right_note_name, right_freq, duration)

                elif event_type == 'mono':
                    note = event['note']
                    duration = event['duration']
                    velocity = event.get('velocity', 100)
                    self.play_mono_note(note, duration, velocity)

                    # Emit signal for mono note
                    note_name = self.midi_to_note_name(note)
                    frequency = self.midi_to_frequency(note)
                    self.note_played.emit(note_name, frequency, duration)
                
                elif event_type == 'pitchbend':
                    channel = event['channel']
                    semitones = event['semitones']
                    self.apply_pitch_bend(channel, semitones)
            
            # Update progress
            progress = int((i / len(stereo_notes)) * 100)
            self.progress_update.emit(progress)
        
        self.playing = False
        self.progress_update.emit(0)
        
    def play_note_on_channel(self, midi_note, duration_ms, channel, velocity=100):
        """Play a MIDI note on specific channel with velocity"""
        # Note: Arduino doesn't support volume control yet, velocity is ignored
        
        frequency = self.midi_to_frequency(midi_note)
        command = f"FREQ,{frequency:.2f},{duration_ms},{channel}"
        
        # Track active note for pitch bend
        self.active_notes[channel] = midi_note
        
        return self.arduino.send_command(command)
    
    def play_chord(self, note1, note2, duration_ms, vel1=100, vel2=100):
        """Play two notes simultaneously as a chord with velocity"""
        # Note: Arduino doesn't support volume control yet, velocities are ignored
        
        freq1 = self.midi_to_frequency(note1)
        freq2 = self.midi_to_frequency(note2)
        # Send both commands
        self.arduino.send_command(f"FREQ,{freq1:.2f},{duration_ms},0")
        self.arduino.send_command(f"FREQ,{freq2:.2f},{duration_ms},1")
        return True
    
    def play_mono_note(self, midi_note, duration_ms, velocity=100):
        """Play the same note on both channels with velocity"""
        # Note: Arduino doesn't support volume control yet, velocity is ignored
        # Use MONO command to play on both channels simultaneously without interference
        command = f"MONO,{midi_note},{duration_ms}"
        return self.arduino.send_command(command)
    
    def _extract_notes(self, midi_file):
        """Extract notes with actual durations from MIDI file"""
        notes = []
        current_tempo = 500000  # Default MIDI tempo
        
        for track in midi_file.tracks:
            current_time = 0
            active_notes = {}  # Track note_on events: (note, channel) -> (start_time, velocity)
            
            for msg in track:
                current_time += msg.time
                
                if msg.type == 'set_tempo':
                    current_tempo = msg.tempo
                
                if msg.type == 'note_on' and msg.velocity > 0:
                    # Skip drum channel
                    if hasattr(msg, 'channel') and msg.channel == 9:
                        continue
                    
                    time_seconds = mido.tick2second(current_time, midi_file.ticks_per_beat, current_tempo)
                    key = (msg.note, msg.channel if hasattr(msg, 'channel') else 0)
                    active_notes[key] = (time_seconds, msg.velocity)
                
                elif (msg.type == 'note_off') or (msg.type == 'note_on' and msg.velocity == 0):
                    # Skip drum channel
                    if hasattr(msg, 'channel') and msg.channel == 9:
                        continue
                    
                    key = (msg.note, msg.channel if hasattr(msg, 'channel') else 0)
                    if key in active_notes:
                        start_time, velocity = active_notes[key]
                        end_time = mido.tick2second(current_time, midi_file.ticks_per_beat, current_tempo)
                        duration = end_time - start_time
                        # Store note with actual duration in milliseconds
                        notes.append((start_time, msg.note, velocity, int(duration * 1000)))
                        del active_notes[key]
        
        return sorted(notes, key=lambda x: x[0])
    
    def _assign_stereo_channels(self, notes, stereo_mode, bass_threshold):
        """Assign notes to left/right channels and group simultaneous events"""
        stereo_events = []
        # Notes format: (time, note, velocity, duration)
        
        # Group notes by time (with small tolerance for "simultaneous" notes)
        time_groups = []
        current_group = []
        last_time = -1
        time_tolerance = 0.05  # 50ms tolerance
        
        for note_time, note, velocity, duration in notes:
            if current_group and abs(note_time - last_time) > time_tolerance:
                time_groups.append((last_time, current_group))
                current_group = []
            
            current_group.append((note, velocity, duration))
            last_time = note_time
        
        if current_group:
            time_groups.append((last_time, current_group))
        
        # Process each time group
        for i, (group_time, group_notes) in enumerate(time_groups):
            events = []
            
            if len(group_notes) == 1:
                # Single note - use actual duration from MIDI file
                note, velocity, duration = group_notes[0]
                # Enforce minimum duration for audibility
                base_duration = max(80, duration)
                
                if stereo_mode in ['mono', 'sync']:
                    # Play same note on both channels for fuller sound using MONO command
                    events.append({
                        'type': 'mono',
                        'note': note,
                        'duration': base_duration,
                        'velocity': velocity
                    })
                else:
                    channel = self._assign_channel(note, stereo_mode, bass_threshold)
                    events.append({
                        'type': 'note',
                        'note': note,
                        'duration': base_duration,
                        'channel': channel,
                        'velocity': velocity
                    })
            
            elif len(group_notes) == 2:
                # Two notes - play as chord or separate channels
                note1, vel1, dur1 = group_notes[0]
                note2, vel2, dur2 = group_notes[1]
                # Use average duration for chord
                base_duration = max(80, int((dur1 + dur2) / 2))
                
                if stereo_mode == "chord":
                    events.append({
                        'type': 'chord',
                        'note1': note1,
                        'note2': note2,
                        'duration': base_duration,
                        'vel1': vel1,
                        'vel2': vel2
                    })
                else:
                    # Assign to different channels
                    events.append({
                        'type': 'note',
                        'note': note1,
                        'duration': base_duration,
                        'channel': 0,  # Left
                        'velocity': vel1
                    })
                    events.append({
                        'type': 'note',
                        'note': note2,
                        'duration': base_duration,
                        'channel': 1,  # Right
                        'velocity': vel2
                    })
            
            else:
                # Multiple notes - select best two
                group_notes.sort(key=lambda x: x[1], reverse=True)  # Sort by velocity
                note1, vel1, dur1 = group_notes[0]  # Loudest
                note2, vel2, dur2 = group_notes[1]  # Second loudest
                # Use average duration for chord
                base_duration = max(80, int((dur1 + dur2) / 2))
                
                events.append({
                    'type': 'chord',
                    'note1': note1,
                    'note2': note2,
                    'duration': base_duration,
                    'vel1': vel1,
                    'vel2': vel2
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
    
    def midi_to_note_name(self, midi_note):
        """Convert MIDI note to name"""
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        octave = (midi_note // 12) - 1
        note = notes[midi_note % 12]
        return f"{note}{octave}"
    
    def apply_pitch_bend(self, channel, semitones):
        """Apply pitch bend to active note on channel"""
        if self.active_notes[channel] is None:
            return  # No active note on this channel
        
        # Calculate bent frequency
        base_note = self.active_notes[channel]
        bent_note = base_note + semitones  # Can be fractional
        target_freq = self.midi_to_frequency(bent_note)
        
        # Send bend command (200ms bend duration for smooth transition)
        bend_duration = 200
        command = f"BEND,{channel},{target_freq:.2f},{bend_duration}"
        self.arduino.send_command(command)
    
    def midi_to_frequency(self, midi_note):
        """Convert MIDI note to frequency (can handle fractional notes for pitch bend)"""
        return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))

class ArduinoSynthGUI(QMainWindow):
    """Main GUI application"""
    
    def __init__(self):
        super().__init__()
        self.arduino = ArduinoConnection()
        self.midi_player = ArduinoStereoMidiPlayer(self.arduino)
        # Favorites and selection state
        self.favorites = set()
        self.all_songs = []
        self.current_song_path = None
        self.setup_ui()
        self.setup_connections()
        
    def setup_ui(self):
        """Setup the user interface"""
        self.setWindowTitle("Arduino MIDI Synthesizer GUI")
        self.setGeometry(100, 100, 1400, 900)
        # Enable maximize button and fullscreen
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        
        # Apply modern dark theme
        self.setStyleSheet("""
            QMainWindow { 
                background-color: #1e1e1e; 
            }
            QWidget { 
                background-color: #1e1e1e; 
                color: #e0e0e0; 
                font-family: 'Segoe UI', 'San Francisco', 'Helvetica Neue', Arial, sans-serif;
            }
            QGroupBox { 
                font-weight: 600; 
                border: 1px solid #3f3f3f;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
                background-color: transparent;
                color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: #4a9eff;
                background-color: transparent;
            }
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 500;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #4a9eff;
            }
            QPushButton:pressed {
                background-color: #1a1a1a;
            }
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #2d2d2d;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #4a9eff;
                border: 2px solid #4a9eff;
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #5aafff;
                border: 2px solid #5aafff;
            }
            QTabWidget::pane {
                border: 1px solid #3f3f3f;
                border-radius: 8px;
                background-color: #252525;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #a0a0a0;
                padding: 10px 20px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #252525;
                color: #4a9eff;
                font-weight: 600;
            }
            QTabBar::tab:hover {
                background-color: #353535;
            }
            QLineEdit {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 6px;
                padding: 8px;
                color: #e0e0e0;
            }
            QLineEdit:focus {
                border: 1px solid #4a9eff;
            }
            QListWidget {
                background-color: #252525;
                border: 1px solid #3f3f3f;
                border-radius: 6px;
                outline: none;
            }
            QListWidget::item {
                border: none;
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #2d4a7c;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background-color: #2d2d2d;
            }
            QComboBox {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 6px;
                padding: 6px 10px;
                color: #e0e0e0;
            }
            QComboBox:hover {
                border: 1px solid #4a9eff;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #a0a0a0;
                margin-right: 5px;
            }
            QSpinBox {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 6px;
                padding: 6px;
                color: #e0e0e0;
            }
            QSpinBox:focus {
                border: 1px solid #4a9eff;
            }
            QProgressBar {
                border: none;
                border-radius: 4px;
                background-color: #2d2d2d;
                text-align: center;
                color: #e0e0e0;
            }
            QProgressBar::chunk {
                background-color: #4a9eff;
                border-radius: 4px;
            }
            QScrollBar:vertical {
                border: none;
                background: #1e1e1e;
                width: 12px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #3f3f3f;
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #4a9eff;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                border: none;
                background: #1e1e1e;
                height: 12px;
            }
            QScrollBar::handle:horizontal {
                background: #3f3f3f;
                border-radius: 6px;
                min-width: 30px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #4a9eff;
            }
            QTextEdit {
                background-color: #1a1a1a;
                border: 1px solid #3f3f3f;
                border-radius: 6px;
                color: #e0e0e0;
            }
            QLabel {
                color: #e0e0e0;
            }
            QFrame {
                background-color: transparent;
                border: none;
            }
        """)
        
        # Central widget with splitter
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        
        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left panel - Controls
        left_panel = self.create_control_panel()
        splitter.addWidget(left_panel)
        
        # Right panel - Visualizer
        right_panel = self.create_visualizer_panel()
        splitter.addWidget(right_panel)
        
        # Set splitter proportions
        splitter.setSizes([400, 1000])
        
        # Status bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready - Connect to Arduino to begin")
        
    def create_control_panel(self):
        """Create the control panel with collapsible sections - peak Apple UX"""
        # Create scroll area with smooth scrolling
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.NoFrame)
        
        # Create panel content
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # Connection section - always visible
        conn_group = self.create_section("Arduino Connection", expanded=True)
        conn_layout = QVBoxLayout()
        conn_group.content_layout.addLayout(conn_layout)
        
        self.port_combo = QComboBox()
        self.refresh_ports()
        self.port_combo.setEditable(True)
        conn_layout.addWidget(QLabel("Port:"))
        conn_layout.addWidget(self.port_combo)
        
        # Add refresh ports button
        refresh_ports_btn = QPushButton("Refresh Ports")
        refresh_ports_btn.clicked.connect(self.refresh_ports)
        conn_layout.addWidget(refresh_ports_btn)
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.connect_btn)
        
        self.connection_status = QLabel("Status: Disconnected")
        conn_layout.addWidget(self.connection_status)
        
        # Add frequency test button
        test_freq_btn = QPushButton("Test High Frequencies")
        test_freq_btn.clicked.connect(self.test_high_frequencies)
        conn_layout.addWidget(test_freq_btn)
        
        layout.addWidget(conn_group)
        
        # MIDI File section - expanded by default
        midi_group = self.create_section("MIDI Playback", expanded=True)
        midi_layout = QVBoxLayout()
        midi_group.content_layout.addLayout(midi_layout)
        
        # Search/filter
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type to filter songs...")
        self.search_input.textChanged.connect(self.apply_song_filter)
        search_layout.addWidget(self.search_input)
        midi_layout.addLayout(search_layout)
        
        # Tabs: All and Favorites
        self.songs_tabs = QTabWidget()
        
        # All songs tab
        all_tab = QWidget()
        all_layout = QVBoxLayout(all_tab)
        all_layout.setContentsMargins(0, 0, 0, 0)
        self.file_list_all = QListWidget()
        self.file_list_all.setMinimumHeight(300)  # Taller list
        self.file_list_all.itemClicked.connect(self.on_song_clicked)
        all_layout.addWidget(self.file_list_all)
        self.songs_tabs.addTab(all_tab, "All")
        
        # Favorites tab
        fav_tab = QWidget()
        fav_layout = QVBoxLayout(fav_tab)
        fav_layout.setContentsMargins(0, 0, 0, 0)
        self.file_list_fav = QListWidget()
        self.file_list_fav.setMinimumHeight(300)  # Taller list
        self.file_list_fav.itemClicked.connect(self.on_song_clicked)
        fav_layout.addWidget(self.file_list_fav)
        self.songs_tabs.addTab(fav_tab, "Favorites ★")
        
        self.songs_tabs.setMinimumHeight(350)  # Make tabs taller overall
        midi_layout.addWidget(self.songs_tabs)
        
        # Buttons
        file_buttons = QHBoxLayout()
        self.load_btn = QPushButton("Load File…")
        self.load_btn.clicked.connect(self.load_midi_file)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_midi_files)
        file_buttons.addWidget(self.load_btn)
        file_buttons.addWidget(self.refresh_btn)
        midi_layout.addLayout(file_buttons)
        
        # Initialize lists
        self.load_favorites()
        self.refresh_midi_files()
        
        # Stereo mode selection
        midi_layout.addWidget(QLabel("Stereo Mode:"))
        self.stereo_mode_combo = QComboBox()
        self.stereo_mode_combo.addItems(['auto', 'bass_split', 'chord', 'random', 'alternate', 'mono', 'sync'])
        self.stereo_mode_combo.currentTextChanged.connect(self.update_stereo_mode)
        midi_layout.addWidget(self.stereo_mode_combo)
        
        # Bass threshold
        midi_layout.addWidget(QLabel("Bass Threshold:"))
        self.bass_threshold_spin = QSpinBox()
        self.bass_threshold_spin.setRange(20, 80)
        self.bass_threshold_spin.setValue(60)
        self.bass_threshold_spin.setSuffix(" (MIDI note)")
        self.bass_threshold_spin.valueChanged.connect(self.update_bass_threshold)
        midi_layout.addWidget(self.bass_threshold_spin)
        
        # Playback controls
        playback_buttons = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.play_midi)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_midi)
        playback_buttons.addWidget(self.play_btn)
        playback_buttons.addWidget(self.stop_btn)
        midi_layout.addLayout(playback_buttons)
        
        # Tempo control
        midi_layout.addWidget(QLabel("Tempo:"))
        self.tempo_slider = QSlider(Qt.Horizontal)
        self.tempo_slider.setRange(25, 300)
        self.tempo_slider.setValue(100)
        self.tempo_slider.valueChanged.connect(self.update_tempo)
        midi_layout.addWidget(self.tempo_slider)
        
        self.tempo_label = QLabel("100%")
        midi_layout.addWidget(self.tempo_label)
        
        # Volume control
        midi_layout.addWidget(QLabel("Volume:"))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 255)
        self.volume_slider.setValue(200)
        self.volume_slider.valueChanged.connect(self.update_volume)
        midi_layout.addWidget(self.volume_slider)
        
        self.volume_label = QLabel("200 (78%)")
        midi_layout.addWidget(self.volume_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        midi_layout.addWidget(self.progress_bar)
        
        layout.addWidget(midi_group)
        
        # Manual controls section - collapsed by default
        manual_group = self.create_section("Manual Controls", expanded=False)
        manual_layout = QVBoxLayout()
        manual_group.content_layout.addLayout(manual_layout)
        
        # Note buttons
        notes_layout = QGridLayout()
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        self.note_buttons = {}
        
        for i, note in enumerate(note_names):
            btn = QPushButton(note)
            btn.clicked.connect(lambda checked, n=note: self.play_manual_note(n))
            notes_layout.addWidget(btn, i // 4, i % 4)
            self.note_buttons[note] = btn
        
        manual_layout.addLayout(notes_layout)
        
        # Octave control
        octave_layout = QHBoxLayout()
        octave_layout.addWidget(QLabel("Octave:"))
        self.octave_spin = QSpinBox()
        self.octave_spin.setRange(1, 8)
        self.octave_spin.setValue(4)
        octave_layout.addWidget(self.octave_spin)
        manual_layout.addLayout(octave_layout)
        
        # Chord buttons
        chord_layout = QHBoxLayout()
        self.chord_c_btn = QPushButton("C Major")
        self.chord_c_btn.clicked.connect(lambda: self.play_chord([60, 64, 67]))
        self.chord_g_btn = QPushButton("G Major")
        self.chord_g_btn.clicked.connect(lambda: self.play_chord([67, 71, 74]))
        chord_layout.addWidget(self.chord_c_btn)
        chord_layout.addWidget(self.chord_g_btn)
        manual_layout.addLayout(chord_layout)
        
        layout.addWidget(manual_group)
        
        # Current note display - always visible, compact
        note_group = self.create_section("Now Playing", expanded=True)
        note_layout = QVBoxLayout()
        note_group.content_layout.addLayout(note_layout)
        
        self.current_note_label = QLabel("---")
        self.current_note_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.current_note_label.setAlignment(Qt.AlignCenter)
        note_layout.addWidget(self.current_note_label)
        
        self.current_freq_label = QLabel("--- Hz")
        self.current_freq_label.setAlignment(Qt.AlignCenter)
        note_layout.addWidget(self.current_freq_label)
        
        layout.addWidget(note_group)
        
        # Add stretch to push everything up
        layout.addStretch()
        
        # Set the panel as the scroll area's widget
        scroll_area.setWidget(panel)
        return scroll_area
    
    def create_section(self, title, expanded=True):
        """Create a collapsible section with modern macOS-style design"""
        section = QFrame()
        section.setObjectName("section_widget")
        section.setStyleSheet("""
            QFrame#section_widget {
                background-color: #252525;
                border: 1px solid #3f3f3f;
                border-radius: 8px;
            }
        """)
        
        main_layout = QVBoxLayout(section)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header button (clickable to collapse/expand)
        header = QPushButton()
        header.setObjectName("section_header")
        header.setText(title)
        header.setCheckable(True)
        header.setChecked(expanded)
        header.setStyleSheet("""
            QPushButton#section_header {
                background-color: transparent;
                border: none;
                border-bottom: 1px solid #3f3f3f;
                border-radius: 0;
                text-align: left;
                padding: 12px 16px;
                font-weight: 600;
                font-size: 13px;
                color: #4a9eff;
            }
            QPushButton#section_header:hover {
                background-color: rgba(74, 158, 255, 0.1);
            }
        """)
        
        # Content container
        content = QFrame()
        content.setObjectName("section_content")
        content.setStyleSheet("QFrame#section_content { background-color: transparent; border: none; }")
        section.content_layout = QVBoxLayout(content)
        section.content_layout.setContentsMargins(16, 12, 16, 12)
        section.content_layout.setSpacing(8)
        
        content.setVisible(expanded)
        
        # Connect toggle
        def toggle_section():
            is_expanded = header.isChecked()
            content.setVisible(is_expanded)
            # Update arrow
            arrow = "▼" if is_expanded else "▶"
            header.setText(f"{arrow}  {title}")
        
        header.clicked.connect(toggle_section)
        toggle_section()  # Set initial state
        
        main_layout.addWidget(header)
        main_layout.addWidget(content)
        
        return section
    
    def create_visualizer_panel(self):
        """Create the visualizer panel"""
        # Use the AudioVisualizer widget
        self.visualizer = AudioVisualizer()
        return self.visualizer
    
    def setup_connections(self):
        """Setup signal connections"""
        self.arduino.status_update.connect(self.update_status)
        self.arduino.connection_changed.connect(self.connection_changed)
        self.midi_player.progress_update.connect(self.progress_bar.setValue)
        self.midi_player.status_update.connect(self.update_status)
        self.midi_player.note_played.connect(self.handle_midi_note_played)
        self.midi_player.chord_played.connect(self.handle_chord_played)
        
        # Connect visualizer to MIDI player
        self.midi_player.visualizer = self.visualizer
    
    def toggle_connection(self):
        """Toggle Arduino connection"""
        if self.arduino.connected:
            self.arduino.disconnect_arduino()
        else:
            # Get the actual port device from the combo box data
            port_data = self.port_combo.currentData()
            if port_data:
                port = port_data
            else:
                # Fallback to current text if no data
                port = self.port_combo.currentText()
            self.arduino.port = port
            self.arduino.connect_arduino()
    
    def connection_changed(self, connected):
        """Handle connection state change"""
        if connected:
            self.connect_btn.setText("Disconnect")
            self.connection_status.setText("Status: Connected")
            self.connection_status.setStyleSheet("color: #00ff00;")
        else:
            self.connect_btn.setText("Connect")
            self.connection_status.setText("Status: Disconnected")
            self.connection_status.setStyleSheet("color: #ff0000;")
    
    def refresh_ports(self):
        """Refresh the list of available serial ports"""
        self.port_combo.clear()
        ports = ArduinoConnection.get_available_ports()
        
        if ports:
            for port in ports:
                display_text = f"{port['device']} - {port['description']}"
                self.port_combo.addItem(display_text, port['device'])
            
            # Set default port
            default_port = ArduinoConnection.get_default_port()
            if default_port:
                for i in range(self.port_combo.count()):
                    if self.port_combo.itemData(i) == default_port:
                        self.port_combo.setCurrentIndex(i)
                        break
        else:
            # Fallback if no ports detected
            fallback_ports = ['/dev/ttyUSB0', '/dev/ttyACM0', '/dev/cu.usbmodem1101', 'COM3']
            for port in fallback_ports:
                self.port_combo.addItem(port)
    
    def test_high_frequencies(self):
        """Test high frequency notes to verify improvements"""
        if not self.arduino.connected:
            QMessageBox.warning(self, "Warning", "Please connect to Arduino first!")
            return
        
        self.update_status("Testing high frequencies...")
        
        # Test high MIDI notes (C8 = 108, C9 = 120)
        high_notes = [96, 100, 104, 108, 112, 116, 120]  # C7 to C9
        note_names = ['C7', 'E7', 'G7', 'C8', 'E8', 'G8', 'C9']
        
        for i, (note, name) in enumerate(zip(high_notes, note_names)):
            frequency = 440.0 * (2.0 ** ((note - 69) / 12.0))
            self.update_status(f"Testing {name} ({frequency:.1f}Hz)")
            
            # Play on both channels
            self.arduino.send_command(f"FREQ,{frequency:.2f},300,0")
            self.arduino.send_command(f"FREQ,{frequency:.2f},300,1")
            
            # Update visualizer
            self.visualizer.play_mono_note(name, frequency, 300)
            
            # Wait between notes
            import time
            time.sleep(0.4)
        
        self.update_status("High frequency test complete!")
    
    def refresh_midi_files(self):
        """Refresh MIDI file list"""
        midi_extensions = ['.mid', '.midi', '.MID', '.MIDI']
        # Collect files
        files = []
        for ext in midi_extensions:
            files.extend([str(p) for p in Path('.').glob(f"*{ext}")])
        self.all_songs = sorted(files, key=lambda s: s.lower())
        # Rebuild lists
        self.build_song_lists()
    
    def build_song_lists(self):
        """Build All and Favorites lists with pinned favorites at top in All"""
        # Clear lists
        self.file_list_all.clear()
        self.file_list_fav.clear()
        
        # Apply filter
        filter_text = self.search_input.text().strip().lower() if hasattr(self, 'search_input') else ''
        def visible(path):
            return filter_text in Path(path).name.lower()
        
        # Favorites pinned first
        favs = [p for p in self.all_songs if p in self.favorites and visible(p)]
        non_favs = [p for p in self.all_songs if p not in self.favorites and visible(p)]
        
        for p in favs + non_favs:
            self.add_song_item(self.file_list_all, p)
        
        # Favorites tab
        for p in favs:
            self.add_song_item(self.file_list_fav, p)
    
    def apply_song_filter(self, _text):
        self.build_song_lists()
    
    def add_song_item(self, list_widget, path):
        """Add a song row with a clickable star button"""
        item = QListWidgetItem()
        item.setData(Qt.UserRole, path)
        # Widget for item with modern styling
        w = QWidget()
        w.setStyleSheet("""
            QWidget {
                background-color: transparent;
                border-radius: 6px;
            }
            QWidget:hover {
                background-color: rgba(255, 255, 255, 0.05);
            }
        """)
        hl = QHBoxLayout(w)
        hl.setContentsMargins(12, 10, 12, 10)  # More padding
        name_label = QLabel(Path(path).name)
        name_label.setStyleSheet("""
            color: #e0e0e0; 
            font-size: 13px;
            font-weight: 500;
            background: transparent;
        """)
        hl.addWidget(name_label)
        hl.addStretch()
        # Star button
        star_btn = QPushButton()
        star_btn.setCheckable(True)
        is_fav = path in self.favorites
        star_btn.setChecked(is_fav)
        star_btn.setText('★' if is_fav else '☆')
        star_btn.setFixedSize(35, 30)  # Bigger button size
        star_btn.setStyleSheet("""QPushButton { 
            font-size: 20px; 
            color: #ffd700; 
            background: transparent; 
            border: 0; 
            padding: 0;
        } 
        QPushButton:hover { 
            color: #ffea00; 
            background: rgba(255, 215, 0, 0.15);
            border-radius: 4px;
        }
        QPushButton:pressed { 
            color: #ffff00; 
            background: rgba(255, 215, 0, 0.25);
        }""")
        star_btn.clicked.connect(lambda checked, p=path: self.toggle_favorite(p))
        hl.addWidget(star_btn)
        w.setLayout(hl)
        
        # Set size hint with more height to prevent clipping
        item.setSizeHint(QSize(w.sizeHint().width(), 50))  # Fixed height
        
        # Set selection colors
        item.setBackground(QColor(0, 0, 0, 0))  # Transparent by default
        
        list_widget.addItem(item)
        list_widget.setItemWidget(item, w)
    
    def toggle_favorite(self, path):
        if path in self.favorites:
            self.favorites.remove(path)
        else:
            self.favorites.add(path)
        self.save_favorites()
        self.build_song_lists()
    
    def load_favorites(self):
        try:
            fav_path = Path.home() / '.unosynth_favorites.json'
            if fav_path.exists():
                import json
                with fav_path.open('r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.favorites = set(data)
        except Exception as e:
            print(f"Failed to load favorites: {e}")
    
    def save_favorites(self):
        try:
            fav_path = Path.home() / '.unosynth_favorites.json'
            import json
            with fav_path.open('w') as f:
                json.dump(sorted(list(self.favorites)), f, indent=2)
        except Exception as e:
            print(f"Failed to save favorites: {e}")
    
    def on_song_clicked(self, item):
        path = item.data(Qt.UserRole)
        self.current_song_path = path
        self.update_status(f"Selected: {Path(path).name}")
    
    def load_midi_file(self):
        """Load MIDI file from dialog"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select MIDI File", 
            ".", 
            "MIDI Files (*.mid *.midi *.MID *.MIDI)"
        )
        
        if file_path:
            # Add to library if not present
            if file_path not in self.all_songs:
                self.all_songs.append(file_path)
                self.all_songs = sorted(self.all_songs, key=lambda s: s.lower())
            self.build_song_lists()
            self.current_song_path = file_path
            self.midi_player.load_file(file_path)
            self.update_status(f"Loaded: {os.path.basename(file_path)}")
    
    def play_midi(self):
        """Play selected MIDI file"""
        # Resolve selected path if any
        if not self.current_song_path:
            # Try selected in 'All' tab
            item = self.file_list_all.currentItem()
            if item:
                self.current_song_path = item.data(Qt.UserRole)
            else:
                # Try selected in 'Favorites'
                item = self.file_list_fav.currentItem()
                if item:
                    self.current_song_path = item.data(Qt.UserRole)
        
        if self.current_song_path:
            self.midi_player.load_file(self.current_song_path)
        else:
            QMessageBox.information(self, "Select a file", "Please select a MIDI file to play.")
            return
        
        if not self.arduino.connected:
            QMessageBox.warning(self, "Warning", "Please connect to Arduino first!")
            return
        
        self.midi_player.play()
    
    def stop_midi(self):
        """Stop MIDI playback"""
        self.midi_player.stop()
        self.visualizer.stop_all_notes()
    
    def update_tempo(self, value):
        """Update tempo multiplier"""
        multiplier = value / 100.0
        self.midi_player.set_tempo(multiplier)
        self.tempo_label.setText(f"{value}%")
    
    def update_stereo_mode(self, mode):
        """Update stereo mode"""
        self.midi_player.set_stereo_mode(mode)
        self.update_status(f"Stereo mode: {mode}")
    
    def update_bass_threshold(self, threshold):
        """Update bass threshold"""
        self.midi_player.set_bass_threshold(threshold)
        self.update_status(f"Bass threshold: {threshold}")
    
    def update_volume(self, value):
        """Update volume on Arduino"""
        if self.arduino.connected:
            self.arduino.send_command(f"VOLUME,{value}")
            percentage = int((value / 255.0) * 100)
            self.volume_label.setText(f"{value} ({percentage}%)")
            self.update_status(f"Volume set to {value} ({percentage}%)")
        else:
            self.volume_label.setText(f"{value} ({int((value/255.0)*100)}%)")
    
    def play_manual_note(self, note_name):
        """Play manual note"""
        if not self.arduino.connected:
            QMessageBox.warning(self, "Warning", "Please connect to Arduino first!")
            return
        
        # Convert note name to MIDI number
        note_map = {'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4, 'F': 5, 
                   'F#': 6, 'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11}
        
        octave = self.octave_spin.value()
        midi_note = (octave + 1) * 12 + note_map[note_name]
        
        # Use FREQ command for better precision
        frequency = 440.0 * (2.0 ** ((midi_note - 69) / 12.0))
        self.arduino.send_command(f"FREQ,{frequency:.2f},500,0")
        self.arduino.send_command(f"FREQ,{frequency:.2f},500,1")
        
        # Update display and visualizer
        note_display = f"{note_name}{octave}"
        self.update_current_note(note_display, frequency)
        self.visualizer.play_mono_note(note_display, frequency, 500)
    
    def play_chord(self, notes):
        """Play chord"""
        if not self.arduino.connected:
            QMessageBox.warning(self, "Warning", "Please connect to Arduino first!")
            return
        
        # Play first two notes as stereo chord
        if len(notes) >= 2:
            # Use FREQ commands for better precision
            left_freq = 440.0 * (2.0 ** ((notes[0] - 69) / 12.0))
            right_freq = 440.0 * (2.0 ** ((notes[1] - 69) / 12.0))
            self.arduino.send_command(f"FREQ,{left_freq:.2f},800,0")
            self.arduino.send_command(f"FREQ,{right_freq:.2f},800,1")
            
            # Update visualizer with chord
            left_note = self.midi_to_note_name(notes[0])
            right_note = self.midi_to_note_name(notes[1])
            
            self.visualizer.play_chord_notes(left_note, left_freq, right_note, right_freq, 800)
        
        # Update display
        note_names = [self.midi_to_note_name(note) for note in notes[:2]]
        self.update_current_note(" + ".join(note_names), 0)
    
    def midi_to_note_name(self, midi_note):
        """Convert MIDI note to name"""
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        octave = (midi_note // 12) - 1
        note = notes[midi_note % 12]
        return f"{note}{octave}"
    
    def handle_midi_note_played(self, note_name, frequency, duration):
        """Handle MIDI note played event"""
        self.update_current_note(note_name, frequency)
        self.visualizer.play_mono_note(note_name, frequency, duration)
    
    def handle_chord_played(self, left_note, left_freq, right_note, right_freq, duration):
        """Handle chord played event"""
        self.visualizer.play_chord_notes(left_note, left_freq, right_note, right_freq, duration)
        self.update_current_note(f"{left_note} + {right_note}", 0)
    
    def update_current_note(self, note_name, frequency):
        """Update current note display"""
        self.current_note_label.setText(note_name)
        if frequency > 0:
            self.current_freq_label.setText(f"{frequency:.1f} Hz")
        else:
            self.current_freq_label.setText("Chord")
    
    def update_status(self, message):
        """Update status bar"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.status_bar.showMessage(f"[{timestamp}] {message}")
    
    def closeEvent(self, event):
        """Handle window close"""
        self.midi_player.stop()
        self.arduino.disconnect_arduino()
        event.accept()

def main():
    """Main function"""
    app = QApplication(sys.argv)
    app.setApplicationName("Arduino MIDI Synthesizer")
    
    # Create and show main window
    window = ArduinoSynthGUI()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
