import pyaudio
from states.asleep import Asleep
from states.listening import Listening
from dotenv import load_dotenv
import RPi.GPIO as GPIO
from light import Light
import subprocess
import os
from sys import argv
from persona import Persona

load_dotenv()

LED_PIN = 20


class Gandalf:
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        persona_name = argv[1] if len(argv) > 1 else "gandalf"
        try:
            self.persona = Persona(persona_name)
        except FileNotFoundError as e:
            print(f"'{e.filename}' does not exist.")
            exit(-1)
        except KeyError as e:
            print(f"'{e.args[0]}' key missing from persona file.")
            exit(-1)

        dir_path = os.path.dirname(os.path.realpath(__file__))
        if os.getenv('APP_ENV') != "LOCAL":
            file_path = os.path.join(dir_path, f"assets/{self.persona.startup_sound}")
            subprocess.call(["xdg-open", file_path])
        self.light = Light(LED_PIN)
        self.light.blink(2)

        self.states = [
            Asleep(self.persona.wake_words),
            Listening(self.light, self.persona)
        ]
        self.current_state = 0

    def run(self):
        try:
            while True:
                self.states[self.current_state].run()
                self.current_state = (self.current_state + 1) % len(self.states)
        except KeyboardInterrupt:
            print("Cleaning up and exiting...")
            GPIO.cleanup()


if __name__ == "__main__":
    gandalf = Gandalf()
    gandalf.run()
