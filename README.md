A little project of mine.

Came to my mind when I broke my guitar jack cable. Tried to wire it to my Arduino Uno's digital pins and it worked, so after countless restless nights I made this.

# UnoSynth - an Arduino Uno midi player

## Setup

### 1. Identify your wires

Before we start, skin(alive) a 3.5 audio jack cable, you'll see red and green or red and blue(-ish?) wires, if I recall correctly RED will be your LEFT and GREEN/BLUE will be your RIGHT channel.

The bronze(uncolored) wire will be your GROUND.

### 2. Software Dependencies

Download or clone this thing, install dependencies from the requirements.

### 3. Wiring

- Wire left channel to Digital Pin 9
- Wire right channel to Digital Pin 10
- Wire ground to any GND on your arduino
- *Optional:* Wire a LED to pin 13 if you want

I prefer to wrap the wires around the ends of those arduino wires and plug the other end in the Uno. It is not that stable, but gets the job done, I guess.

### 4. Flash the Arduino

Flash *synth.ino* from the synth folder.

### 5. Connect and Play

1. Open the *arduino_synth_gui_v2.py*
2. Click **connect** in the top left corner
3. You should see that status has been updated to **connected**
   - If not, close everything might be talking to the board's serial (like Serial Monitor/Plotter in Arduino IDE)
4. Put midi files in the same directory as the python program is
5. **Hit refresh** - you should see your midi's in the collection after that
6. **Hit play** and it should start playing
