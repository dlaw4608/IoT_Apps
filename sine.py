import numpy as np
import sounddevice as sd

# Sine wave parameters
frequency = 440.0  # A4 pitch
duration = 5.0     # seconds
sample_rate = 48000

# Generate sine wave
t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
wave = 0.2 * np.sin(2 * np.pi * frequency * t)

# Play it
print("Playing 440 Hz sine wave...")
sd.play(wave, samplerate=sample_rate)
sd.wait()
print("Done.")
