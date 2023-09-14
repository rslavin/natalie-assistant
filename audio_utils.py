import wave
import numpy as np
from scipy.signal import resample
import os
import openai
from pydub import AudioSegment
import math


def amplify_wav(file_path, amplification_factor):
    with wave.open(file_path, 'rb') as wf:
        params = wf.getparams()
        audio_data = wf.readframes(params.nframes)
        audio_as_np_int16 = np.frombuffer(audio_data, dtype=np.int16)
        audio_as_np_int16 = np.int16(audio_as_np_int16 * amplification_factor)
        amplified_data = audio_as_np_int16.tobytes()

    with wave.open(file_path, 'wb') as wf:
        wf.setparams(params)
        wf.writeframes(amplified_data)


def adjust_volume(file_path, percentage, file_format="mp3"):
    # Load the audio file
    sound = AudioSegment.from_file(file_path, format=file_format)

    # Calculate the gain in dB
    gain_db = 20 * math.log10(1 + percentage / 100)

    # Apply the gain
    amplified_sound = sound.apply_gain(gain_db)

    # Save the new audio file (here, it overwrites the original; you may choose to save as a different file)
    amplified_sound.export(file_path, format=file_format)


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


def frequency_filter(frame, cutoff_low=15, cutoff_high=250, sample_rate=16000):
    """
    Uses fast fourier transform to filter out frequencies outside of human speech.
    :param frame: Frame to filter
    :param cutoff_low: Lower frequency bound
    :param cutoff_high: Upper frequency bound
    :param sample_rate: Sample rate
    :return: Filtered frame
    """
    amplification_factor = 4.5
    # Perform the FFT
    sp = np.fft.fft(frame)
    freq = np.fft.fftfreq(len(sp), 1 / sample_rate)

    # Zero out frequencies outside the desired cutoff range
    sp[(freq < cutoff_low)] = 0
    sp[(freq > cutoff_high)] = 0

    # Perform the Inverse FFT to get back to time domain
    filtered_frame = np.fft.ifft(sp).real
    filtered_frame *= amplification_factor  # amplify since the filtered audio will no longer be normalized
    return filtered_frame


def transcribe_audio(file_path):
    with open(file_path, "rb") as audio_file:
        # TODO TRANSCRIPTION interface
        # TODO timeout, try https://pypi.org/project/retry/
        question_text = openai.Audio.transcribe(
            file=audio_file,
            model="whisper-1",
            response_format="text",
            language="en"
        )
    os.remove(file_path)
    return question_text