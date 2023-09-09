import wave
import pyaudio
import time
import openai
import os
from gpt_client import GptClient
from .state_interface import State
from tts import play_gandalf
import webrtcvad
from scipy.signal import resample
import numpy as np
import traceback
import time

RATE = 44100
VOICE_DETECTION_RATE = 32000  # voice detection rate to be downsampled to
CHANNELS = 1
SILENCE_THRESHOLD = 70
VOICE_ACTIVITY_THRESHOLD = 2  # 1 gives more false positives, 3 gives more false negatives
FRAMES_PER_BUFFER = 1026
MAX_DURATION = 10
PAUSE_TIME = 3
TMP_COMMAND_FILE = "tmp.wav"


def downsample_audio(audio_data, from_rate, to_rate):
    if not audio_data:
        return None

    # Convert to numpy array if audio_data is in bytes
    if isinstance(audio_data, bytes):
        audio_data = np.frombuffer(audio_data, dtype=np.int16)

    audio_data = np.array(audio_data)
    ratio = to_rate / from_rate
    audio_len = len(audio_data)
    new_len = int(audio_len * ratio)
    resampled_audio = resample(audio_data, new_len)
    return np.int16(resampled_audio)


# TODO extract this to a separate file and split it into individual functions for clarity
# TODO never mind, thank you, what time is it?, thanks, repeat that, no thanks, set your volume to X%
def local_commands(query: str):
    """
    Return a tuple where the first element dictates what to do with the command and the second element is either
    a query (which may be modified) or None if the query should be dropped.A
    For the first value: -1 => drop the query, 0 => continue with getting a response, 1 => use this response instead
    :param query:
    :return:
    """
    query_stripped = query.strip(".?! \t\n")
    print(f"Filtering '{query_stripped}'")
    # empty string
    alpha_string = ''.join(e for e in query_stripped if e.isalpha())
    if not len(alpha_string) or alpha_string.lower().endswith(("nevermind", "forgetit", "thankyou")):
        return -1, None

    # time
    if query_stripped.lower() == "what time is it":
        t = time.localtime()
        current_time = time.strftime("%I:%M", t)
        return 1, f"It is {current_time}."

    return 0, query


class Listening(State):

    def __init__(self, light):
        self.gpt = GptClient()
        self.light = light
        self.vad = webrtcvad.Vad(VOICE_ACTIVITY_THRESHOLD)

    def run(self):
        while True:
            voice_detected = False
            self.light.turn_on()
            print("Entering Listening state.")

            pa = pyaudio.PyAudio()
            audio_stream = None

            try:
                audio_stream = pa.open(
                    rate=RATE,
                    channels=CHANNELS,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=FRAMES_PER_BUFFER,
                )

                wf = wave.open(TMP_COMMAND_FILE, 'wb')
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
                wf.setframerate(RATE)

                # record
                audio_stream.start_stream()

                frames = []
                start_time = time.time()
                silence_since = time.time()
                frame_length = int(VOICE_DETECTION_RATE * 0.01)
                while time.time() - start_time <= MAX_DURATION:
                    data = audio_stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False)
                    downsampled_data = downsample_audio(data, RATE, VOICE_DETECTION_RATE)

                    if downsampled_data is not None:
                        if silence_since is not None and time.time() - silence_since >= PAUSE_TIME:
                            break

                        for i in range(0, len(downsampled_data), frame_length):
                            frame = downsampled_data[i:i + frame_length]

                            if len(frame) == frame_length:
                                try:
                                    if self.vad.is_speech(frame.tobytes(), VOICE_DETECTION_RATE):
                                        print("Voice detected")
                                        silence_since = time.time()
                                        voice_detected = True
                                except Exception as e:
                                    print(f"Error in WebRTC VAD: {e}")
                                    continue

                    frames.append(data)
                if not voice_detected:
                    print("No speech detected. Existing state...")
                    self.light.turn_off()
                    break

                # write audio to the file
                wf.writeframes(b''.join(frames))
                wf.close()
                self.light.begin_pulse()

                # transcribe .wav with whisper
                print("Transcribing audio...")
                start_time = time.time()
                with open(TMP_COMMAND_FILE, "rb") as audio_file:
                    # TODO TRANSCRIPTION interface
                    question_text = openai.Audio.transcribe(
                        file=audio_file,
                        model="whisper-1",
                        response_format="text",
                        language="en"
                    )
                os.remove(TMP_COMMAND_FILE)
                transcribe_time = time.time() - start_time
                print(f"Transcription complete ({transcribe_time} seconds)")
                print(f"I heard '{question_text}'")

                action, question_text = local_commands(question_text)
                if action == -1:  # drop
                    print("Filtered.")
                    self.light.turn_off()
                    return False
                elif action == 1:  # replace
                    print("Answering locally...")
                    response = question_text
                else:  # get the answer from the llm
                    # send transcribed query to gpt
                    print("Asking LLM...")
                    start_time = time.time()
                    # TODO LLM interface
                    response = self.gpt.send_message(question_text)
                    gpt_time = time.time() - start_time
                    print(f"GPT request complete ({gpt_time} seconds)")
                    if response == "-1":
                        self.light.turn_off()
                        return False

                # convert the gpt text to speech
                print("Converting gpt text to speech...")
                # TODO check if this light stuff is taking too long
                self.light.turn_off()
                # TODO TTS interface
                play_gandalf(response)

            except Exception as e:
                print(f"An error occurred: {e}")
                traceback.print_exc()
                return False

            finally:
                if audio_stream is not None:
                    audio_stream.stop_stream()
                    audio_stream.close()
                    self.light.turn_off()
                pa.terminate()

        return True
