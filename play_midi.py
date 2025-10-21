import serial
import time

# Replace with your Arduino port, e.g., '/dev/ttyUSB0' on Linux or 'COM3' on Windows
ARDUINO_PORT = '/dev/cu.usbmodem1101'
BAUD_RATE = 9600

# Note frequencies (A4 = 440 Hz)
NOTE_FREQUENCIES = {
    'C4': 261,
    'D4': 294,
    'E4': 329,
    'F4': 349,
    'G4': 392,
    'A4': 440,
    'B4': 493,
}

# Duration of each note in milliseconds
NOTE_DURATION = 500


def play_note_on_arduino(note):
    frequency = NOTE_FREQUENCIES.get(note)
    if frequency:
        command = f"{frequency},{NOTE_DURATION}\n"
        arduino.write(command.encode())
        print(f"Sent: {command.strip()}")
    else:
        print(f"Note {note} not found.")


def main():
    global arduino
    
    # Initialize serial connection
    arduino = serial.Serial(ARDUINO_PORT, BAUD_RATE)
    time.sleep(2)  # Wait for the connection to establish
    
    # Play notes C4 to B4
    for note in ['C4', 'D4', 'E4', 'F4', 'G4', 'A4', 'B4']:
        play_note_on_arduino(note)
        time.sleep(NOTE_DURATION / 1000)
        
    arduino.close()


if __name__ == "__main__":
    main()
