/*
 * Arduino STEREO MIDI Synthesizer
 * Receives commands via serial to play tones on two channels
 * Commands:
 * - FREQ,DURATION[,CHANNEL] - Play frequency for duration in ms on channel (0=left, 1=right, default=0)
 * - NOTE,MIDI_NUM,DURATION[,CHANNEL] - Play MIDI note on channel
 * - CHORD,NOTE1,NOTE2,DURATION - Play two notes simultaneously
 * - MONO,MIDI_NUM,DURATION - Play same note on both channels (true mono)
 * - STOP[,CHANNEL] - Stop current tone on channel (no channel = stop both)
 * - STATUS - Get current status
 */

#include <Arduino.h>

const int LEFT_SPEAKER_PIN = 9;   // Left channel
const int RIGHT_SPEAKER_PIN = 10; // Right channel
const int LED_PIN = 13;

// Track state for both channels
boolean isPlaying[2] = {false, false};
unsigned long noteStartTime[2] = {0, 0};
unsigned long noteDuration[2] = {0, 0};
float currentFreq[2] = {0, 0};

void setup() {
  Serial.begin(9600);
  pinMode(LEFT_SPEAKER_PIN, OUTPUT);
  pinMode(RIGHT_SPEAKER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  
  // Startup sequence - stereo test
  digitalWrite(LED_PIN, HIGH);
  tone(LEFT_SPEAKER_PIN, 440, 200);  // A4 on left
  delay(250);
  tone(RIGHT_SPEAKER_PIN, 554, 200); // C#5 on right
  delay(250);
  digitalWrite(LED_PIN, LOW);
  
  Serial.println("Arduino STEREO Synth Ready!");
  Serial.println("Commands: FREQ,DURATION[,CHANNEL] | NOTE,MIDI,DURATION[,CHANNEL] | CHORD,NOTE1,NOTE2,DURATION | STOP[,CHANNEL] | STATUS");
  Serial.println("Channels: 0=Left, 1=Right");
}

void loop() {
  // CRITICAL: Generate tones as frequently as possible
  generateTones();
  
  // Only check timing/serial occasionally to avoid interrupting tone generation
  static unsigned long lastCheck = 0;
  unsigned long now = millis();
  
  if (now - lastCheck >= 10) {  // Check every 10ms instead of every loop
    lastCheck = now;
    
    // Check if notes should stop on either channel
    for (int channel = 0; channel < 2; channel++) {
      if (isPlaying[channel] && now - noteStartTime[channel] >= noteDuration[channel]) {
        stopChannel(channel);
      }
    }
    
    // Update LED based on activity
    digitalWrite(LED_PIN, isPlaying[0] || isPlaying[1]);
    
    // Process serial commands
    if (Serial.available() > 0) {
      String input = Serial.readStringUntil('\n');
      input.trim();
      processCommand(input);
    }
  }
}

void processCommand(String command) {
  command.toUpperCase();
  
  if (command.startsWith("FREQ,")) {
    // Format: FREQ,frequency,duration[,channel]
    parseFreqCommand(command);
  }
  else if (command.startsWith("NOTE,")) {
    // Format: NOTE,midi_note,duration[,channel]
    parseNoteCommand(command);
  }
  else if (command.startsWith("CHORD,")) {
    // Format: CHORD,note1,note2,duration
    parseChordCommand(command);
  }
  else if (command.startsWith("MONO,")) {
    // Format: MONO,midi_note,duration
    parseMonoCommand(command);
  }
  else if (command.startsWith("STOP")) {
    // Format: STOP[,channel]
    parseStopCommand(command);
  }
  else if (command == "STATUS") {
    printStatus();
  }
  else {
    // Legacy format: frequency,duration (plays on left channel)
    int separatorIndex = command.indexOf(',');
    if (separatorIndex > 0) {
      int frequency = command.substring(0, separatorIndex).toInt();
      int duration = command.substring(separatorIndex + 1).toInt();
      playToneOnChannel(frequency, duration, 0);
      Serial.println("[Legacy] Playing: " + String(frequency) + "Hz for " + String(duration) + "ms on LEFT");
    } else {
      Serial.println("Unknown command: " + command);
    }
  }
}

void parseFreqCommand(String command) {
  int firstComma = command.indexOf(',');
  int secondComma = command.indexOf(',', firstComma + 1);
  int thirdComma = command.indexOf(',', secondComma + 1);
  
  if (firstComma > 0 && secondComma > firstComma) {
    int frequency = command.substring(firstComma + 1, secondComma).toInt();
    int duration;
    int channel = 0; // Default to left channel
    
    if (thirdComma > secondComma) {
      duration = command.substring(secondComma + 1, thirdComma).toInt();
      channel = command.substring(thirdComma + 1).toInt();
    } else {
      duration = command.substring(secondComma + 1).toInt();
    }
    
    if (channel >= 0 && channel <= 1) {
      playToneOnChannel(frequency, duration, channel);
      // Reduced serial output to prevent blocking
      // Serial.println("Playing: " + String(frequency) + "Hz for " + String(duration) + "ms on " + channelName(channel));
    }
  }
}

void parseNoteCommand(String command) {
  int firstComma = command.indexOf(',');
  int secondComma = command.indexOf(',', firstComma + 1);
  int thirdComma = command.indexOf(',', secondComma + 1);
  
  if (firstComma > 0 && secondComma > firstComma) {
    int midiNote = command.substring(firstComma + 1, secondComma).toInt();
    int duration;
    int channel = 0; // Default to left channel
    
    if (thirdComma > secondComma) {
      duration = command.substring(secondComma + 1, thirdComma).toInt();
      channel = command.substring(thirdComma + 1).toInt();
    } else {
      duration = command.substring(secondComma + 1).toInt();
    }
    
    if (channel >= 0 && channel <= 1) {
      float frequency = midiToFrequency(midiNote);
      playToneOnChannel(frequency, duration, channel);
      // Reduced serial output to prevent blocking
      // Serial.println("Playing MIDI " + String(midiNote) + ": " + String(frequency) + "Hz for " + String(duration) + "ms on " + channelName(channel));
    }
  }
}

void parseChordCommand(String command) {
  int firstComma = command.indexOf(',');
  int secondComma = command.indexOf(',', firstComma + 1);
  int thirdComma = command.indexOf(',', secondComma + 1);
  
  if (firstComma > 0 && secondComma > firstComma && thirdComma > secondComma) {
    int note1 = command.substring(firstComma + 1, secondComma).toInt();
    int note2 = command.substring(secondComma + 1, thirdComma).toInt();
    int duration = command.substring(thirdComma + 1).toInt();
    
    float freq1 = midiToFrequency(note1);
    float freq2 = midiToFrequency(note2);
    
    playToneOnChannel(freq1, duration, 0); // Left channel
    playToneOnChannel(freq2, duration, 1); // Right channel
    
    // Reduced serial output to prevent blocking
    // Serial.println("Playing CHORD: MIDI " + String(note1) + " (" + String(freq1) + "Hz) LEFT + MIDI " + String(note2) + " (" + String(freq2) + "Hz) RIGHT for " + String(duration) + "ms");
  }
}

void parseMonoCommand(String command) {
  int firstComma = command.indexOf(',');
  int secondComma = command.indexOf(',', firstComma + 1);
  
  if (firstComma > 0 && secondComma > firstComma) {
    int midiNote = command.substring(firstComma + 1, secondComma).toInt();
    int duration = command.substring(secondComma + 1).toInt();
    
    float frequency = midiToFrequency(midiNote);
    
    // Play the same note on both channels simultaneously
    playToneOnChannel(frequency, duration, 0); // Left channel
    playToneOnChannel(frequency, duration, 1); // Right channel
    
    // Reduced serial output to prevent blocking
    // Serial.println("Playing MONO: MIDI " + String(midiNote) + " (" + String(frequency) + "Hz) on BOTH channels for " + String(duration) + "ms");
  }
}

void parseStopCommand(String command) {
  int commaIndex = command.indexOf(',');
  
  if (commaIndex > 0) {
    // Stop specific channel
    int channel = command.substring(commaIndex + 1).toInt();
    if (channel >= 0 && channel <= 1) {
      stopChannel(channel);
      Serial.println("Stopped " + channelName(channel));
    }
  } else {
    // Stop both channels
    stopChannel(0);
    stopChannel(1);
    Serial.println("Stopped BOTH channels");
  }
}

void printStatus() {
  Serial.println("=== STEREO SYNTH STATUS ===");
  for (int i = 0; i < 2; i++) {
    Serial.print(channelName(i) + ": ");
    if (isPlaying[i]) {
      unsigned long remaining = noteDuration[i] - (millis() - noteStartTime[i]);
      Serial.println("Playing " + String(currentFreq[i]) + "Hz, " + String(remaining) + "ms remaining");
    } else {
      Serial.println("Idle");
    }
  }
}

void playToneOnChannel(float frequency, int duration, int channel) {
  int pin = (channel == 0) ? LEFT_SPEAKER_PIN : RIGHT_SPEAKER_PIN;
  
startPWM(pin, frequency);
  isPlaying[channel] = true;
  noteStartTime[channel] = millis();
  noteDuration[channel] = duration;
  currentFreq[channel] = frequency;
}

void stopChannel(int channel) {
  int pin = (channel == 0) ? LEFT_SPEAKER_PIN : RIGHT_SPEAKER_PIN;
  
stopPWM(pin);
  isPlaying[channel] = false;
  currentFreq[channel] = 0;
}

String channelName(int channel) {
  return (channel == 0) ? "LEFT" : "RIGHT";
}

float midiToFrequency(int midiNote) {
  // Convert MIDI note to frequency
  // A4 (MIDI 69) = 440 Hz
  return 440.0 * pow(2.0, (midiNote - 69) / 12.0);
}

// Timer-based tone generation variables
volatile unsigned long lastToggle[2] = {0, 0};
volatile unsigned long toggleInterval[2] = {0, 0};
volatile boolean toneActive[2] = {false, false};
volatile boolean pinState[2] = {false, false};

void startPWM(int pin, float frequency) {
  int channel = (pin == LEFT_SPEAKER_PIN) ? 0 : 1;
  
  if (frequency > 0) {
    // Support full MIDI range: ~8 Hz (MIDI 0) to ~12500 Hz (MIDI 127)
    // Only cap at extremes to prevent Arduino timing issues
    if (frequency > 8000) frequency = 8000;  // Cap at 8kHz (well above MIDI 127)
    if (frequency < 20) frequency = 20;      // Lower limit at 20Hz (sub-bass)
    
    toggleInterval[channel] = (1000000.0 / frequency) / 2.0; // Microseconds for half period
    
    // Ensure minimum interval to prevent timing issues at very high frequencies
    if (toggleInterval[channel] < 62) {  // 62us = ~8kHz max
      toggleInterval[channel] = 62;
    }
    
    toneActive[channel] = true;
    lastToggle[channel] = micros();
  }
}

void stopPWM(int pin) {
  int channel = (pin == LEFT_SPEAKER_PIN) ? 0 : 1;
  toneActive[channel] = false;
  pinState[channel] = false;
  digitalWrite(pin, LOW);
}

void generateTones() {
  unsigned long currentTime = micros();
  
  // Handle left channel (pin 9) - use direct port manipulation for speed
  if (toneActive[0] && (currentTime - lastToggle[0] >= toggleInterval[0])) {
    pinState[0] = !pinState[0];
    // Pin 9 is PORTB bit 1 on Arduino Uno
    if (pinState[0]) {
      PORTB |= (1 << 1);  // Set pin HIGH
    } else {
      PORTB &= ~(1 << 1); // Set pin LOW
    }
    lastToggle[0] = currentTime;
  }
  
  // Handle right channel (pin 10) - use direct port manipulation for speed
  if (toneActive[1] && (currentTime - lastToggle[1] >= toggleInterval[1])) {
    pinState[1] = !pinState[1];
    // Pin 10 is PORTB bit 2 on Arduino Uno
    if (pinState[1]) {
      PORTB |= (1 << 2);  // Set pin HIGH
    } else {
      PORTB &= ~(1 << 2); // Set pin LOW
    }
    lastToggle[1] = currentTime;
  }
}
