#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from tac.core.log_config import setup_logging

class Speech2Text:
    """Dummy class that provides the interface but no actual functionality."""
    
    def __init__(self, client=None, logger=None, audio_recorder=None, offline_model_type=None):
        self.transcript = None
        self.logger = logger if logger else setup_logging('tac.utils.audio.Speech2Text')
        self.is_recording = False
    
    def start_recording(self, output_filename=None, max_time=None):
        """Dummy method for interface compatibility."""
        self.is_recording = True
        self.logger.info("Recording functionality disabled.")
        
    def stop_recording(self, minimum_duration=0.4):
        """Dummy method for interface compatibility."""
        self.is_recording = False
        self.logger.info("Recording functionality disabled.")
        return None
    
    def handle_unmute_button(self, mic_button_state: bool):
        """Dummy method that just returns False."""
        return False

