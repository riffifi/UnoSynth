A little project of mine.
Came to my mind when I broke my guitar jack cable. Tried to wire it to my Arduino Uno's digital pins and it worked, so after countless restless nights I made this.
# UnoSynth - an Arduino Uno midi player

## Setup

### Identify your wires
Before we start, skin(alive) a 3.5 audio jack cable, you'll see red and green or red and blue(-ish?) wires, if I recall correctly RED will be your LEFT and GREEN/BLUE will be your RIGHT channel. 
The bronze(uncolored) wire will be your GROUND.

## Wiring and software
Download or clone this thing, install dependencies from the requirements.
Then wire left channel to Digital Pin 9 and the right one to 10, you can also wire a led to pin 13 if you want.
Wire ground to any GND on your arduino.
I prefer to wrap the wires around the ends of those arduino wires and plug the other end in the Uno. It is not that stable, but gets the job done, I guess.
Next, flash *synth.ino* from the synth folder, after that open the *arduino_synth_gui_v2.py* and click **connect** in the top left corner, you should see that status has been updated to **connected**, if not, close everything might be talking to the board's serial(like Serial Monitor/Plotter in Arduino IDE).
After that, you can put midi files in the same directory as the python program is and **hit refresh**, you should see your midi's in the collection after that. After that just **hit play** and it should start playing.
