import serial
import time
import sys

# --- Configuration ---
ARDUINO_PORT = '/dev/cu.usbmodem1101'  # Adjust this to your actual Arduino port
BAUD_RATE = 9600

# --- Note Definitions (MIDI Numbers) ---
C4 = 60; D4 = 62; E4 = 64; F4 = 65; G4 = 67; A4 = 69; B4 = 71; Bb4 = 70
C5 = 72; D5 = 74; E5 = 76; F5 = 77; G5 = 79; A5 = 81; B5 = 83; Bb5 = 82
C6 = 84; D6 = 86; E6 = 88; F6 = 89; G6 = 91; A6 = 93; B6 = 95
G3 = 55; E4 = 64

# --- Tempo Settings ---
NOTE_DURATION = 150  # Base unit in ms

# --- Melody Definition ---
# Each tuple: (MIDI note, duration in ms), or (None, duration) for rests
MELODY = [
    (E5, NOTE_DURATION), (E5, NOTE_DURATION), (None, NOTE_DURATION // 2), (E5, NOTE_DURATION),
    (None, NOTE_DURATION), (C5, NOTE_DURATION), (E5, NOTE_DURATION), (None, NOTE_DURATION),
    (G5, NOTE_DURATION * 2), (None, NOTE_DURATION * 2),

    (G4, NOTE_DURATION), (None, NOTE_DURATION * 2),
    (C5, NOTE_DURATION), (None, NOTE_DURATION),
    (G4, NOTE_DURATION), (None, NOTE_DURATION),
    (E4, NOTE_DURATION), (None, NOTE_DURATION),

    (A4, NOTE_DURATION), (None, NOTE_DURATION // 2),
    (B4, NOTE_DURATION), (None, NOTE_DURATION // 2),
    (Bb4, NOTE_DURATION), (A4, NOTE_DURATION),

    (G4, NOTE_DURATION), (E5, NOTE_DURATION),
    (G5, NOTE_DURATION), (A5, NOTE_DURATION * 2),
    (F5, NOTE_DURATION), (G5, NOTE_DURATION),
    (None, NOTE_DURATION), (E5, NOTE_DURATION),
    (C5, NOTE_DURATION), (D5, NOTE_DURATION),
    (B4, NOTE_DURATION), (None, NOTE_DURATION * 2),

    # Repeat part of melody
    (C5, NOTE_DURATION), (None, NOTE_DURATION * 2),
    (G4, NOTE_DURATION), (None, NOTE_DURATION * 2),
    (E4, NOTE_DURATION), (None, NOTE_DURATION * 2),
    (A4, NOTE_DURATION), (None, NOTE_DURATION),
    (B4, NOTE_DURATION), (None, NOTE_DURATION),
    (Bb4, NOTE_DURATION), (A4, NOTE_DURATION),

    (G4, NOTE_DURATION), (E5, NOTE_DURATION),
    (G5, NOTE_DURATION), (A5, NOTE_DURATION * 2),
    (F5, NOTE_DURATION), (G5, NOTE_DURATION),
    (None, NOTE_DURATION), (E5, NOTE_DURATION),
    (C5, NOTE_DURATION), (D5, NOTE_DURATION),
    (B4, NOTE_DURATION), (None, NOTE_DURATION * 2),
]

# --- MIDI Note to Frequency Converter ---
def midi_to_frequency(midi_note):
    """Converts MIDI note number to frequency in Hz."""
    if midi_note is None:
        return 0
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))

# --- Melody Playback ---
def play_theme(arduino):
    print("🎵 Playing Super Mario Bros. theme...")
    for note, duration in MELODY:
        if note is not None:
            freq = midi_to_frequency(note)
            command = f"{int(freq)},{int(duration)}\n"
            arduino.write(command.encode())
        time.sleep(duration / 1000 * 1.1)  # Small gap between notes

# --- Main Connection Loop ---
def main():
    try:
        print(f"Connecting to Arduino on port {ARDUINO_PORT}...")
        arduino = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=2)
        time.sleep(2)  # Let Arduino reset
        print("Connected! Starting theme in a loop. Press Ctrl+C to stop.")

        while True:
            play_theme(arduino)
            print("✅ Theme finished. Restarting in 3 seconds...")
            time.sleep(3)

    except serial.SerialException as e:
        print(f"❌ Serial error: Could not connect to {ARDUINO_PORT}.", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⏹ Stopped by user.")
    finally:
        if 'arduino' in locals() and arduino.is_open:
            arduino.close()
            print("🔌 Arduino connection closed.")

# --- Entry Point ---
if __name__ == "__main__":
    main()