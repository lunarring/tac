#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tac.core.log_config import setup_logging
import tempfile
from pydub import AudioSegment
import threading
import os
import time
from openai import OpenAI
import sounddevice as sd
import numpy as np
import wave

logger = setup_logging('tac.utils.audio')

def read_api_key(env_var_name):
    """Read API key from environment variable."""
    return os.environ.get(env_var_name)

class AudioRecorder:
    """
    A class to handle audio recording using sounddevice instead of pyaudio.

    Attributes:
        channels (int): Number of audio channels.
        rate (int): Sampling rate.
        chunk (int): Number of frames per buffer.
        frames (list): List to hold audio frames.
        is_recording (bool): Flag to check if recording is in progress.
        stream (sd.InputStream): Audio stream.
        output_filename (str): Output file name.
    """

    def __init__(
        self,
        channels=1,
        rate=44100,
        chunk=1024,
    ):
        self.channels = channels
        self.rate = rate
        self.chunk = chunk
        self.frames = []
        self.is_recording = False
        self.stream = None
        self.output_filename = None

    def _record(self, max_time=None):
        self.stream = sd.InputStream(
            samplerate=self.rate,
            channels=self.channels,
            blocksize=self.chunk,
            dtype='float32'
        )
        logger.info("Recording...")
        self.frames = []
        start_time = time.time()
        with self.stream:
            while self.is_recording:
                if max_time and (time.time() - start_time) >= max_time:
                    break
                data, overflowed = self.stream.read(self.chunk)
                self.frames.append(data.flatten())

        logger.info("Finished recording.")
        
        # Convert to WAV and then to MP3
        wav_filename = tempfile.mktemp(suffix='.wav')
        wf = wave.open(wav_filename, 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(2)  # 2 bytes for 16-bit audio
        wf.setframerate(self.rate)
        self.frames = np.clip(self.frames, -1, +1)
        wf.writeframes(np.array(self.frames*32767).astype(np.int16).tobytes())
        wf.close()

        wav_audio = AudioSegment.from_wav(wav_filename)
        wav_audio.export(self.output_filename, format="mp3")

    def start_recording(self, output_filename=None, max_time=None):
        if not self.is_recording:
            self.is_recording = True
            if output_filename is None:
                temp_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
                self.output_filename = temp_file.name
                temp_file.close()
            else:
                output_filename = str(output_filename)
                if not output_filename.endswith('.mp3'):
                    raise ValueError("Output filename must have a .mp3 extension")
                self.output_filename = output_filename
            self.thread = threading.Thread(target=self._record, args=(max_time,))
            self.thread.start()

    def stop_recording(self):
        if self.is_recording:
            self.is_recording = False
            self.thread.join()


class Speech2Text:
    def __init__(self, client=None, offline_model_type=None):
        """
        Initialize the Speech2Text with an OpenAI client and an audio recorder.

        Args:
            client: An instance of OpenAI client. If None, it will be created using the OPENAI_API_KEY.
            offline_model_type: An instance of an offline model for speech recognition. If None, it will use the API for transcription.

        Raises:
            ValueError: If no OpenAI API key is found in the environment variables.
        """
        self.transcript = None
        if client is None:
            api_key = read_api_key("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("No OPENAI_API_KEY found in environment variables")
            self.client = OpenAI(api_key=api_key)
        else:
            self.client = client


        
        self.audio_recorder = AudioRecorder()

    def start_recording(self, output_filename=None, max_time=None):
        """
        Start the audio recording.
        Args:
            output_filename (str): The filename for the output file. If None, a temporary file is created.
            max_time (int, optional): Maximum recording time in seconds.
        Raises:
            ValueError: If the audio recorder is not available.
        """
        if self.audio_recorder is None:
            raise ValueError("Audio recorder is not available")
        self.audio_recorder.start_recording(output_filename, max_time)


    def stop_recording(self, minimum_duration=0.4):
        """
Stop the audio recording and check if the recording meets the minimum duration.

Args:
    minimum_duration (float, optional): The minimum duration in seconds for a recording to be valid.
                                      Default is 1 second.

Returns:
    str: The transcribed text if the recording meets the minimum duration requirement, otherwise None.

Raises:
    ValueError: If the audio recorder is not available.
"""
        if self.audio_recorder is None:
            raise ValueError("Audio recorder is not available")
        self.audio_recorder.stop_recording()

        audio_duration = AudioSegment.from_mp3(self.audio_recorder.output_filename).duration_seconds
        if audio_duration < minimum_duration:
            logger.info(f"Recording is too short, only {audio_duration:.2f} seconds. Minimum required is {minimum_duration} seconds.")
            return None
        return self.translate(self.audio_recorder.output_filename)
    
    def translate(self, audio_filepath):
        """
        Translate the audio file to text using OpenAI's translation model.

        Args:
            audio_filepath: The file path of the audio file to be translated.

        Returns:
            str: The transcribed text.

        Raises:
            FileNotFoundError: If the audio file does not exist.
        """
        if not os.path.exists(audio_filepath):
            raise FileNotFoundError(f"Audio file not found: {audio_filepath}")

        with open(audio_filepath, "rb") as audio_file:
            transcript = self.client.audio.translations.create(
                model="whisper-1", 
                file=audio_file
            )
            return transcript.text
   
if __name__ == "__main__":
    audio_recorder = AudioRecorder()
    speech_detector = Speech2Text()

    speech_detector.start_recording()
    time.sleep(3)
    translation = speech_detector.stop_recording()
    print(f"translation: {translation}")