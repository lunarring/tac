#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tempfile
from pydub import AudioSegment
import threading
import os
import time
from openai import OpenAI
from lunar_tools.logprint import LogPrint
import simpleaudio
from elevenlabs.client import ElevenLabs
from elevenlabs import Voice, VoiceSettings, play, save
import sounddevice as sd
import numpy as np
import wave
from pydub import AudioSegment
from lunar_tools.utils import read_api_key

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
        logger: A logging instance. If None, a default logger will be used.
    """

    def __init__(
        self,
        channels=1,
        rate=44100,
        chunk=1024,
        logger=None
    ):
        self.channels = channels
        self.rate = rate
        self.chunk = chunk
        self.frames = []
        self.is_recording = False
        self.stream = None
        self.output_filename = None
        self.logger = logger if logger else LogPrint()

    def _record(self, max_time=None):
        self.stream = sd.InputStream(
            samplerate=self.rate,
            channels=self.channels,
            blocksize=self.chunk,
            dtype='float32'
        )
        self.logger.print("Recording...")
        self.frames = []
        start_time = time.time()
        with self.stream:
            while self.is_recording:
                if max_time and (time.time() - start_time) >= max_time:
                    break
                data, overflowed = self.stream.read(self.chunk)
                self.frames.append(data.flatten())

        self.logger.print("Finished recording.")
        
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
    def __init__(self, client=None, logger=None, audio_recorder=None, offline_model_type=None):
        """
        Initialize the Speech2Text with an OpenAI client, a logger, and an audio recorder.

        Args:
            client: An instance of OpenAI client. If None, it will be created using the OPENAI_API_KEY.
            logger: A logging instance. If None, a default logger will be used.
            audio_recorder: An instance of an audio recorder. If None, recording functionalities will be disabled.
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

        if offline_model_type is not None:
            import whisper
            self.whisper_model = whisper.load_model(offline_model_type)
            self.offline_mode = True
        else:
            self.offline_mode = False
        
        self.logger = logger if logger else LogPrint()

        if audio_recorder is None:
            self.audio_recorder = AudioRecorder(logger=logger)
        else:
            self.audio_recorder = audio_recorder

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
            self.logger.print(f"Recording is too short, only {audio_duration:.2f} seconds. Minimum required is {minimum_duration} seconds.")
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
        if self.offline_mode:
            audio_segment = AudioSegment.from_file(audio_filepath)
            # Convert audio_segment to a numpy array
            # Note: Pydub's samples are interleaved, so for multi-channel audio, every Nth sample is a sample from a different channel
            numpydata = np.array(audio_segment.get_array_of_samples()).astype(np.int16)
            numpydata = np.hstack(numpydata).astype(np.float32)
            numpydata = numpydata.astype(np.float32) / 32768.0  # Convert to float32 in range [-1, 1]
            options = dict(language="english", beam_size=5, best_of=5)
            translate_options = dict(task="translate", **options)
            result = self.whisper_model.transcribe(numpydata, **translate_options)
            return result["text"].strip()
        else:
            with open(audio_filepath, "rb") as audio_file:
                transcript = self.client.audio.translations.create(
                    model="whisper-1", 
                    file=audio_file
                )
                return transcript.text
            
    def handle_unmute_button(self, mic_button_state: bool):
        if mic_button_state:
            if not self.audio_recorder.is_recording:
                self.start_recording()
        else:
            if self.audio_recorder.is_recording:
                try:
                    transcript = self.stop_recording()
                    transcript = transcript.strip().lower()
                    self.transcript = transcript
                    return True
                except Exception as e:
                    print(f"Error stopping recording: {e}")
        return False


class Text2SpeechOpenAI:
    def __init__(
        self, 
        client=None, 
        logger=None, 
        voice_model="nova", 
        sound_player=None,
        blocking_playback=False
    ):
        """
        Initialize the Text2Speech with an OpenAI client, a logger, a text source, a default voice model, and optionally a sound player.
        """
        if client is None:
            api_key = read_api_key("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("No OPENAI_API_KEY found in environment variables")
            self.client = OpenAI(api_key=api_key)
        else:
            self.client = client
        self.logger = logger if logger else LogPrint()
        # Initialize the sound player only if provided
        self.sound_player = sound_player
        self.output_filename = None  # Initialize output filename
        self.voice_model = voice_model
        self.blocking_playback = blocking_playback

    def play(self, text=None):
        """
        Play a generated speech file. Instantiates SoundPlayer if it's not already.
        """
        self.generate(text)
        if self.sound_player is None:
            self.sound_player = SoundPlayer(blocking_playback=self.blocking_playback)
        self.sound_player.play_sound(self.output_filename)

    def stop(self):
        """
        Stop the currently playing speech file.
        """
        if self.sound_player:
            self.sound_player.stop_sound()


    def generate(self, text, output_filename=None):
        """
        Generate speech from text.
    
        Args:
            text (str): The text to be converted into speech. 
            output_filename (str): The filename for the output file. If None, a default filename is used.
    
        Raises:
            ValueError: If the text source is not available.
        """
        if text is None or len(text)==0:
            raise ValueError("text is invalid!")
    
        response = self.client.audio.speech.create(
            model="tts-1",
            voice=self.voice_model,
            input=text
        )
        
        self.output_filename = output_filename if output_filename else "output_speech.mp3"
        response.stream_to_file(self.output_filename)
        self.logger.print(f"Generated speech saved to {self.output_filename}")


    def change_voice(self, new_voice):
        """
        Change the voice model for speech generation.

        Args:
            new_voice (str): The new voice model to be used.
        """
        if new_voice in self.list_available_voices():
            self.voice_model = new_voice
            self.logger.print(f"Voice model changed to {new_voice}")
        else:
            raise ValueError(f"Voice '{new_voice}' is not a valid voice model.")

    @staticmethod
    def list_available_voices():
        """
        List the available voice models.

        Returns:
            list: A list of available voice models.
        """
        return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    
    
class Text2SpeechElevenlabs:
    def __init__(
        self,
        logger=None,
        sound_player=None,
        voice_id=None,
        blocking_playback=False
    ):
        """
        Initialize the Text2Speech for elevenlabs, a optional logger and optionally a sound player.
        """
        self.client = ElevenLabs(api_key=read_api_key("ELEVEN_API_KEY"))
        self.logger = logger if logger else LogPrint()
        # Initialize the sound player only if provided
        self.sound_player = sound_player
        self.output_filename = None  # Initialize output filename
        self.default_voice_id = "EXAVITQu4vr4xnSDxMaL"
        if voice_id is None:
            self.voice_id = self.default_voice_id
        else:
            self.voice_id = voice_id
        self.blocking_playback = blocking_playback

    def play(
            self,
            text,
            output_filename=None,
            stability=0.71,
            similarity_boost=0.5,
            style=0.0,
            use_speaker_boost=True
            ):
        """
        Play a generated speech file. Instantiates SoundPlayer if it's not already.
        """
        self.generate(text, output_filename, self.voice_id, stability, similarity_boost, style, use_speaker_boost)
        if self.sound_player is None:
            self.sound_player = SoundPlayer(blocking_playback=self.blocking_playback)
        self.sound_player.play_sound(self.output_filename)

    def change_voice(self, voice_id):
        """
        Change the voice model for speech generation.

        Args:
            new_voice (str): The new voice model to be used.
        """
        self.voice_id = voice_id
        self.logger.print(f"Voice model changed to {voice_id}")    

    def stop(self):
        """
        Stop the currently playing speech file.
        """
        if self.sound_player:
            self.sound_player.stop_sound()


    def generate(
            self,
            text,
            output_filename=None,
            voice_id=None,
            stability=0.71,
            similarity_boost=0.5,
            style=0.0,
            use_speaker_boost=True
            ):
        """
        Generate speech from text.
    
        Args:
            text (str): The text to be converted into speech. 
            output_filename (str): The filename for the output file. If None, a default filename is used.
            voice_id (str): The ID for the voice to be used. If None, a default voice ID is used.
            stability (float): Stability setting for voice generation.
            similarity_boost (float): Similarity boost setting for voice generation.
            style (float): Style setting for voice generation.
            use_speaker_boost (bool): Flag to use speaker boost in voice generation.
    
        Raises:
            ValueError: If the text source is not available.
        """
        if text is None or len(text) == 0:
            raise ValueError("text is invalid!")
    
        if voice_id is None:
            voice_id = self.default_voice_id
        
            
    
        audio = self.client.generate(
            text=text,
            voice=Voice(
                voice_id=self.voice_id,
                settings=VoiceSettings(stability=stability, similarity_boost=similarity_boost, style=style, use_speaker_boost=True)
            )
        )
    
        self.output_filename = output_filename if output_filename else "output_speech.mp3"
        save(audio, self.output_filename)
        self.logger.print(f"Generated speech saved to {self.output_filename}")





class SoundPlayer:
    def __init__(self, blocking_playback=False):
        self._play_thread = None
        self._playback_object = None
        self.blocking_playback = blocking_playback

    def _play_sound_threaded(self, sound):
        self._playback_object = simpleaudio.play_buffer(
            sound.raw_data,
            num_channels=sound.channels,
            bytes_per_sample=sound.sample_width,
            sample_rate=sound.frame_rate
        )
        self._playback_object.wait_done()  # Wait until sound has finished playing

    def play_sound(self, file_path, pan_value=0):
        # Stop any currently playing sound
        self.stop_sound()

        # Load the sound file
        sound = AudioSegment.from_file(file_path)
        
        # play sound from left/right speaker
        if pan_value != 0 and pan_value > -1 and pan_value < 1:
            sound = sound.pan(pan_value)

        # Start a new thread for playing the sound
        self._play_thread = threading.Thread(target=self._play_sound_threaded, args=(sound,))
        self._play_thread.start()
        if self.blocking_playback:
            self._play_thread.join()

    def stop_sound(self):
        if self._play_thread and self._play_thread.is_alive():
            if self._playback_object:
                self._playback_object.stop()
            self._play_thread.join()

    

#%% EXAMPLE USE        
if __name__ == "__main__":
    audio_recorder = AudioRecorder()
    # audio_recorder.start_recording("x.mp3")
    # time.sleep(2)
    # audio_recorder.stop_recording()
    
    # audio_recorder.start_recording("myvoice2.mp3")
    # time.sleep(3)
    # audio_recorder.stop_recording()
    
    
    audio_recorder = AudioRecorder()
    speech_detector = Speech2Text(audio_recorder=audio_recorder)
    # speech_detector = Speech2Text(offline_model_type='large-v3')

    #%%

    speech_detector.start_recording()
    time.sleep(3)
    translation = speech_detector.stop_recording()
    print(f"translation: {translation}")
    
    # speech_detector.start_recording()
    # time.sleep(3)
    # translation = speech_detector.stop_recording()
    # print(f"translation: {translation}")
    
    # # Example Usage
    # text2speech = Text2SpeechElevenlabs(blocking_playback=True)
    # text2speech.play("hello")
    
    # text2speech.change_voice("FU5JW1L0DwfWILWkNpW6")
    # text2speech.play("well how are you we are making this very long test of sound playback but is it blocking")
    
    
    # # text2speech.change_voice("nova")
    # # player = SoundPlayer()
    # # player.play_sound("/tmp/bla.mp3")
    # # player.stop_sound()
    
    # # %%
    
    # from elevenlabs import clone, generate, play

    # voice = clone(
    #     name="buba",
    #     description="buba",
    #     files=["jlong.mp3"],
    # )
    
    # audio = generate(text="I am not sure!", voice=voice)
    
    # play(audio)
    

