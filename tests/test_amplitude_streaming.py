import numpy as np
from tac.utils.audio import AudioRecorder

def test_compute_amplitude():
    # create a dummy audio chunk with known values
    data_chunk = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype='float32')
    # expected RMS = sqrt(mean([0^2,0.5^2,0.5^2,1^2,1^2])) = sqrt((0 +0.25+0.25+1+1)/5) = sqrt(2.5/5) = sqrt(0.5)
    expected = (0.5) ** 0.5
    amplitude = AudioRecorder.compute_amplitude(data_chunk)
    assert abs(amplitude - expected) < 1e-6

def test_amplitude_callback_invocation():
    # Test that the amplitude callback is called with a computed amplitude.
    recorded_amplitudes = []
    def amplitude_callback(val):
        recorded_amplitudes.append(val)
    recorder = AudioRecorder()
    recorder.set_amplitude_callback(amplitude_callback)
    # simulate a data chunk read
    dummy_chunk = np.array([0.0, 0.25, -0.25, 0.5, -0.5], dtype='float32')
    # Manually call callback as _record loop would do
    amplitude = AudioRecorder.compute_amplitude(dummy_chunk)
    if recorder.amplitude_callback:
        recorder.amplitude_callback(amplitude)
    assert len(recorded_amplitudes) == 1
    assert abs(recorded_amplitudes[0] - amplitude) < 1e-6