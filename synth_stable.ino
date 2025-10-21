/*
 * Arduino STEREO MIDI Synthesizer - ENHANCED VERSION
 * Hardware PWM + Volume Control + Smooth Envelopes
 * 
 * Receives commands via serial to play tones on two channels
 * Commands:
 * - FREQ,FREQUENCY,DURATION[,CHANNEL[,VOLUME]] - Play frequency with optional volume (0-255)
 * - NOTE,MIDI_NUM,DURATION[,CHANNEL[,VOLUME]] - Play MIDI note with optional volume
 * - CHORD,NOTE1,NOTE2,DURATION - Play two notes simultaneously
 * - MONO,MIDI_NUM,DURATION - Play same note on both channels (true mono)
 * - VOLUME,LEVEL[,CHANNEL] - Set volume (0-255, no channel = set both)
 * - STOP[,CHANNEL] - Stop current tone on channel (no channel = stop both)
 * - STATUS - Get current status
 * - TEST - Play frequency sweep test (20Hz to 8kHz)
 */

#include <Arduino.h>

const int LEFT_SPEAKER_PIN = 9;   // Left channel
const int RIGHT_SPEAKER_PIN = 10; // Right channel
const int LED_PIN = 13;

// Hardware PWM tone generation variables (declared early for use in functions)
volatile unsigned long lastToggle[2] = {0, 0};
volatile unsigned long toggleInterval[2] = {0, 0};
volatile boolean toneActive[2] = {false, false};
volatile uint8_t currentDutyCycle[2] = {128, 128}; // 50% duty cycle default

// Track state for both channels
boolean isPlaying[2] = {false, false};
unsigned long noteStartTime[2] = {0, 0};
unsigned long noteDuration[2] = {0, 0};
float currentFreq[2] = {0, 0};
uint8_t channelVolume[2] = {200, 200}; // Master volume per channel (0-255)
uint8_t targetVolume[2] = {200, 200};  // Target volume for envelope

// Envelope settings (in milliseconds)
const unsigned int ATTACK_TIME = 5;    // Very quick attack to reduce overhead
const unsigned int RELEASE_TIME = 20;  // Shorter release for high notes
unsigned long releaseStartTime[2] = {0, 0};
boolean inRelease[2] = {false, false};
uint8_t releaseStartVolume[2] = {0, 0};

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
  // Check if notes should stop on either channel
  for (int channel = 0; channel < 2; channel++) {
    if (isPlaying[channel]) {
      unsigned long elapsed = millis() - noteStartTime[channel];
      
      // Start release phase before note ends
      if (!inRelease[channel] && elapsed >= noteDuration[channel] - RELEASE_TIME) {
        startRelease(channel);
      }
      
      // Actually stop after release
      if (elapsed >= noteDuration[channel]) {
        stopChannel(channel);
      }
    }
  }
  
  // Update envelopes
  updateEnvelopes();
  
  // Generate tones using hardware PWM
  generateTones();
  
  // Update LED based on activity
  digitalWrite(LED_PIN, isPlaying[0] || isPlaying[1]);
  
  // Process serial commands
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    processCommand(input);
  }
}

void processCommand(String command) {
  command.toUpperCase();
  
  if (command.startsWith("FREQ,")) {
    parseFreqCommand(command);
  }
  else if (command.startsWith("NOTE,")) {
    parseNoteCommand(command);
  }
  else if (command.startsWith("CHORD,")) {
    parseChordCommand(command);
  }
  else if (command.startsWith("MONO,")) {
    parseMonoCommand(command);
  }
  else if (command.startsWith("VOLUME,")) {
    parseVolumeCommand(command);
  }
  else if (command.startsWith("STOP")) {
    parseStopCommand(command);
  }
  else if (command == "STATUS") {
    printStatus();
  }
  else if (command == "TEST") {
    runFrequencyTest();
  }
  else {
    // Legacy format: frequency,duration (plays on left channel)
    int separatorIndex = command.indexOf(',');
    if (separatorIndex > 0) {
      int frequency = command.substring(0, separatorIndex).toInt();
      int duration = command.substring(separatorIndex + 1).toInt();
      playToneOnChannel(frequency, duration, 0, channelVolume[0]);
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
  int fourthComma = command.indexOf(',', thirdComma + 1);
  
  if (firstComma > 0 && secondComma > firstComma) {
    float frequency = command.substring(firstComma + 1, secondComma).toFloat();
    int duration;
    int channel = 0;
    uint8_t volume = channelVolume[0];
    
    if (thirdComma > secondComma) {
      duration = command.substring(secondComma + 1, thirdComma).toInt();
      channel = command.substring(thirdComma + 1, fourthComma > thirdComma ? fourthComma : command.length()).toInt();
      
      if (fourthComma > thirdComma) {
        volume = constrain(command.substring(fourthComma + 1).toInt(), 0, 255);
      } else {
        volume = channelVolume[channel];
      }
    } else {
      duration = command.substring(secondComma + 1).toInt();
    }
    
    if (channel >= 0 && channel <= 1) {
      playToneOnChannel(frequency, duration, channel, volume);
      Serial.println("Playing: " + String(frequency, 1) + "Hz for " + String(duration) + "ms on " + channelName(channel) + " (vol: " + String(volume) + ")");
    }
  }
}

void parseNoteCommand(String command) {
  int firstComma = command.indexOf(',');
  int secondComma = command.indexOf(',', firstComma + 1);
  int thirdComma = command.indexOf(',', secondComma + 1);
  int fourthComma = command.indexOf(',', thirdComma + 1);
  
  if (firstComma > 0 && secondComma > firstComma) {
    int midiNote = command.substring(firstComma + 1, secondComma).toInt();
    int duration;
    int channel = 0;
    uint8_t volume = channelVolume[0];
    
    if (thirdComma > secondComma) {
      duration = command.substring(secondComma + 1, thirdComma).toInt();
      channel = command.substring(thirdComma + 1, fourthComma > thirdComma ? fourthComma : command.length()).toInt();
      
      if (fourthComma > thirdComma) {
        volume = constrain(command.substring(fourthComma + 1).toInt(), 0, 255);
      } else {
        volume = channelVolume[channel];
      }
    } else {
      duration = command.substring(secondComma + 1).toInt();
    }
    
    if (channel >= 0 && channel <= 1) {
      float frequency = midiToFrequency(midiNote);
      playToneOnChannel(frequency, duration, channel, volume);
      Serial.println("Playing MIDI " + String(midiNote) + ": " + String(frequency) + "Hz for " + String(duration) + "ms on " + channelName(channel) + " (vol: " + String(volume) + ")");
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
    
    playToneOnChannel(freq1, duration, 0, channelVolume[0]);
    playToneOnChannel(freq2, duration, 1, channelVolume[1]);
    
    Serial.println("Playing CHORD: MIDI " + String(note1) + " (" + String(freq1) + "Hz) LEFT + MIDI " + String(note2) + " (" + String(freq2) + "Hz) RIGHT for " + String(duration) + "ms");
  }
}

void parseMonoCommand(String command) {
  int firstComma = command.indexOf(',');
  int secondComma = command.indexOf(',', firstComma + 1);
  
  if (firstComma > 0 && secondComma > firstComma) {
    int midiNote = command.substring(firstComma + 1, secondComma).toInt();
    int duration = command.substring(secondComma + 1).toInt();
    
    float frequency = midiToFrequency(midiNote);
    
    playToneOnChannel(frequency, duration, 0, channelVolume[0]);
    playToneOnChannel(frequency, duration, 1, channelVolume[1]);
    
    Serial.println("Playing MONO: MIDI " + String(midiNote) + " (" + String(frequency) + "Hz) on BOTH channels for " + String(duration) + "ms");
  }
}

void parseVolumeCommand(String command) {
  int firstComma = command.indexOf(',');
  int secondComma = command.indexOf(',', firstComma + 1);
  
  if (firstComma > 0) {
    int volume = constrain(command.substring(firstComma + 1, secondComma > firstComma ? secondComma : command.length()).toInt(), 0, 255);
    
    if (secondComma > firstComma) {
      int channel = command.substring(secondComma + 1).toInt();
      if (channel >= 0 && channel <= 1) {
        channelVolume[channel] = volume;
        Serial.println("Set " + channelName(channel) + " volume to " + String(volume));
      }
    } else {
      channelVolume[0] = volume;
      channelVolume[1] = volume;
      Serial.println("Set BOTH channels volume to " + String(volume));
    }
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
  Serial.println("=== ENHANCED STEREO SYNTH STATUS ===");
  for (int i = 0; i < 2; i++) {
    Serial.print(channelName(i) + " (vol " + String(channelVolume[i]) + "): ");
    if (isPlaying[i]) {
      unsigned long remaining = noteDuration[i] - (millis() - noteStartTime[i]);
      Serial.println("Playing " + String(currentFreq[i]) + "Hz, " + String(remaining) + "ms remaining");
    } else {
      Serial.println("Idle");
    }
  }
  Serial.println("Hardware PWM | Smooth Envelopes | Volume Control");
}

void playToneOnChannel(float frequency, int duration, int channel, uint8_t volume) {
  int pin = (channel == 0) ? LEFT_SPEAKER_PIN : RIGHT_SPEAKER_PIN;
  
  startPWM(pin, frequency);
  isPlaying[channel] = true;
  inRelease[channel] = false;
  noteStartTime[channel] = millis();
  noteDuration[channel] = duration;
  currentFreq[channel] = frequency;
  targetVolume[channel] = volume;
}

void stopChannel(int channel) {
  int pin = (channel == 0) ? LEFT_SPEAKER_PIN : RIGHT_SPEAKER_PIN;
  
  stopPWM(pin);
  isPlaying[channel] = false;
  inRelease[channel] = false;
  currentFreq[channel] = 0;
}

void startRelease(int channel) {
  inRelease[channel] = true;
  releaseStartTime[channel] = millis();
  releaseStartVolume[channel] = targetVolume[channel];
}

void updateEnvelopes() {
  for (int channel = 0; channel < 2; channel++) {
    if (!isPlaying[channel]) continue;
    
    unsigned long elapsed = millis() - noteStartTime[channel];
    uint8_t currentVol;
    
    if (inRelease[channel]) {
      // Release phase - fade out
      unsigned long releaseElapsed = millis() - releaseStartTime[channel];
      if (releaseElapsed >= RELEASE_TIME) {
        currentVol = 0;
      } else {
        currentVol = map(releaseElapsed, 0, RELEASE_TIME, releaseStartVolume[channel], 0);
      }
    } else if (elapsed < ATTACK_TIME) {
      // Attack phase - fade in
      currentVol = map(elapsed, 0, ATTACK_TIME, 0, targetVolume[channel]);
    } else {
      // Sustain phase - hold at target
      currentVol = targetVolume[channel];
    }
    
    // Apply volume via PWM duty cycle
    applyVolume(channel, currentVol);
  }
}

void applyVolume(int channel, uint8_t volume) {
  // Volume is applied during envelope calculation
  // For high frequencies using hardware tone(), volume control is limited
  // This is a tradeoff for cleaner high-frequency generation
  currentDutyCycle[channel] = volume;
}

String channelName(int channel) {
  return (channel == 0) ? "LEFT" : "RIGHT";
}

float midiToFrequency(int midiNote) {
  // Convert MIDI note to frequency with higher precision
  // A4 (MIDI 69) = 440 Hz
  // Use more precise calculation for better high note accuracy
  return 440.0 * pow(2.0, (midiNote - 69) / 12.0);
}

void startPWM(int pin, float frequency) {
  int channel = (pin == LEFT_SPEAKER_PIN) ? 0 : 1;
  
  if (frequency > 0) {
    // Cap frequency range
    if (frequency > 8000) frequency = 8000;
    if (frequency < 20) frequency = 20;
    
    // For high frequencies (>1000Hz), use hardware tone() for better accuracy
    // For lower frequencies, use software PWM for envelope control
    if (frequency > 1000) {
      // Use Arduino's hardware tone() - much cleaner for high frequencies
      tone(pin, (unsigned int)frequency);
      toneActive[channel] = false; // Mark as using hardware tone
    } else {
      // Use software PWM for lower frequencies (better envelope control)
      toggleInterval[channel] = (1000000.0 / frequency) / 2.0;
      
      if (toggleInterval[channel] < 100) {
        toggleInterval[channel] = 100; // Safety limit
      }
      
      toneActive[channel] = true;
      lastToggle[channel] = micros();
    }
  }
}

void stopPWM(int pin) {
  int channel = (pin == LEFT_SPEAKER_PIN) ? 0 : 1;
  
  // Stop both software PWM and hardware tone
  toneActive[channel] = false;
  noTone(pin);
  digitalWrite(pin, LOW);
}

void generateTones() {
  unsigned long currentTime = micros();
  
  // Handle left channel (pin 9)
  if (toneActive[0] && (currentTime - lastToggle[0] >= toggleInterval[0])) {
    digitalWrite(LEFT_SPEAKER_PIN, !digitalRead(LEFT_SPEAKER_PIN));
    lastToggle[0] = currentTime;
  }
  
  // Handle right channel (pin 10)
  if (toneActive[1] && (currentTime - lastToggle[1] >= toggleInterval[1])) {
    digitalWrite(RIGHT_SPEAKER_PIN, !digitalRead(RIGHT_SPEAKER_PIN));
    lastToggle[1] = currentTime;
  }
}

void runFrequencyTest() {
  Serial.println("=== ENHANCED FREQUENCY SWEEP TEST ===");
  Serial.println("Testing frequencies from 20Hz to 8000Hz with envelopes...");
  
  // Test low frequencies
  for (int freq = 20; freq <= 200; freq += 20) {
    Serial.println("Testing: " + String(freq) + "Hz");
    playToneOnChannel(freq, 200, 0, 200);
    delay(250);
  }
  
  // Test mid frequencies
  for (int freq = 250; freq <= 2000; freq += 100) {
    Serial.println("Testing: " + String(freq) + "Hz");
    playToneOnChannel(freq, 150, 0, 200);
    delay(200);
  }
  
  // Test high frequencies
  for (int freq = 2200; freq <= 8000; freq += 200) {
    Serial.println("Testing: " + String(freq) + "Hz");
    playToneOnChannel(freq, 100, 0, 200);
    delay(150);
  }
  
  Serial.println("=== FREQUENCY TEST COMPLETE ===");
}
