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
        recording_finished (bool): Flag to check if recording has finished.
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
        self.recording_finished = False

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
                
                # Print diagnostics
                if len(self.frames) % 10 == 0:
                    elapsed = time.time() - start_time
                    logger.debug(f"Recording frames: {len(self.frames)}, elapsed: {elapsed:.2f}s")

        logger.info(f"Finished recording. Captured {len(self.frames)} frames in {time.time() - start_time:.2f} seconds")
        
        # Save directly to WAV format (more reliable than MP3)
        wf = wave.open(self.output_filename, 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(2)  # 2 bytes for 16-bit audio
        wf.setframerate(self.rate)
        
        # Make sure we have frames to write
        if self.frames:
            logger.debug(f"Writing {len(self.frames)} frames to {self.output_filename}")
            self.frames = np.clip(self.frames, -1, +1)
            wf.writeframes(np.array(self.frames*32767).astype(np.int16).tobytes())
            logger.debug(f"File size after writing: {os.path.getsize(self.output_filename)} bytes")
        else:
            logger.warning("No frames captured during recording")
        wf.close()
        
        # Signal that recording has finished and file is ready
        self.recording_finished = True

    def start_recording(self, output_filename=None, max_time=None):
        if not self.is_recording:
            self.is_recording = True
            self.recording_finished = False
            
            if output_filename is None:
                # Save directly to WAV instead of MP3
                temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
                self.output_filename = temp_file.name
                temp_file.close()
            else:
                output_filename = str(output_filename)
                # Accept WAV extension or add it if missing
                if not output_filename.endswith('.wav'):
                    output_filename += '.wav'
                self.output_filename = output_filename
                
            self.thread = threading.Thread(target=self._record, args=(max_time,))
            # Track when we started the thread for minimum duration enforcement
            self.thread.start_time = time.time()
            self.thread.start()
            logger.debug(f"Recording thread started at {self.thread.start_time}")

    def stop_recording(self):
        if self.is_recording:
            # Make sure we have enough frames before stopping
            if hasattr(self, 'thread') and self.thread and self.thread.is_alive():
                # Check if we have enough frames
                min_frames = 20  # Minimum number of frames to have a useful recording
                
                if len(self.frames) < min_frames:
                    logger.info(f"Only {len(self.frames)} frames recorded, waiting for more data...")
                    # Wait a bit to get more frames
                    for _ in range(10):  # Try 10 times with short waits
                        if len(self.frames) >= min_frames:
                            break
                        time.sleep(0.1)  # Short sleep to get more frames
                
                # At this point, stop anyway - user explicitly stopped recording
                logger.info(f"Stopping recording with {len(self.frames)} frames")
            
            # Now stop the recording
            self.is_recording = False
            self.thread.join()
            
            # Wait for file to be fully written
            start_wait = time.time()
            while not self.recording_finished and (time.time() - start_wait) < 3.0:
                time.sleep(0.1)
            
            return self.output_filename

    def cleanup(self):
        """
        Clean up resources, especially temporary files.
        This should be called when an error occurs to ensure resources are freed.
        """
        # Stop recording if still in progress
        if self.is_recording:
            self.is_recording = False
            try:
                self.thread.join(timeout=1.0)  # Wait with timeout
            except Exception:
                pass  # Ignore any thread joining errors
                
        # Close stream if open
        if self.stream and hasattr(self.stream, 'close'):
            try:
                self.stream.close()
            except Exception:
                pass
                
        # Remove temporary output file if it exists
        if self.output_filename and os.path.exists(self.output_filename):
            try:
                os.remove(self.output_filename)
                self.output_filename = None
            except Exception:
                pass
                
        # Clear frames list to free memory
        self.frames = []


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
                                      Default is 0.4 second.

Returns:
    str: The transcribed text if the recording meets the minimum duration requirement, otherwise None.

Raises:
    ValueError: If the audio recorder is not available.
"""
        if self.audio_recorder is None:
            raise ValueError("Audio recorder is not available")
            
        # Get the output filename from stop_recording
        wav_file = self.audio_recorder.stop_recording()
        
        if not wav_file or not os.path.exists(wav_file):
            logger.error(f"Recording failed: output file not found or empty")
            return None
            
        # Check file size
        file_size = os.path.getsize(wav_file)
        if file_size == 0:
            logger.error(f"Recording failed: output file is empty (0 bytes)")
            return None
            
        try:
            # Use pydub to get audio duration from WAV
            audio_duration = AudioSegment.from_wav(wav_file).duration_seconds
            
            if audio_duration < minimum_duration:
                logger.info(f"Recording is too short, only {audio_duration:.2f} seconds. Minimum required is {minimum_duration} seconds.")
                return None
                
            # Transcribe directly using the WAV file
            return self.transcribe_audio(wav_file)
            
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            import traceback
            traceback.print_exc()
            return None
    
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
    
    def transcribe_audio(self, audio_filepath):
        """
        Directly transcribe an audio file without going through the recording process.
        This method is useful when you already have a recorded audio file and just need 
        to transcribe it. It can handle various audio formats supported by OpenAI API.
        
        Args:
            audio_filepath: The file path of the audio file to be transcribed.
            
        Returns:
            str: The transcribed text.
            
        Raises:
            FileNotFoundError: If the audio file does not exist.
        """
        if not os.path.exists(audio_filepath):
            raise FileNotFoundError(f"Audio file not found: {audio_filepath}")
            
        logger.info(f"Transcribing audio file: {audio_filepath}")
        try:
            with open(audio_filepath, "rb") as audio_file:
                # Use transcriptions API endpoint instead of translations
                # This works better for direct audio files
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file
                )
                return transcript.text
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            # Try the translate method as fallback
            return self.translate(audio_filepath)

if __name__ == "__main__":
    audio_recorder = AudioRecorder()
    speech_detector = Speech2Text()

    speech_detector.start_recording()
    time.sleep(3)
    translation = speech_detector.stop_recording()
    print(f"translation: {translation}")