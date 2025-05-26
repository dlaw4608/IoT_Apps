import asyncio
import json
import time
import serial
import threading
import numpy as np
import websockets

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate, MediaStreamTrack
from av import AudioFrame

# Config
SAMPLE_RATE = 48000
DEFAULT_BPM = 60.0
current_heart_rate = DEFAULT_BPM
heart_rate_lock = threading.Lock()


def read_serial(port="/dev/ttyACM0", baudrate=115200):
    global current_heart_rate
    try:
        with serial.Serial(port, baudrate, timeout=1) as ser:
            print(f"Reading from {port} at {baudrate} baud...")
            while True:
                line = ser.readline().decode("utf-8").strip()
                if line:
                    try:
                        data = json.loads(line)
                        new_hr = data.get("pulse")
                        if new_hr:
                            with heart_rate_lock:
                                current_heart_rate = float(new_hr)
                            print(f"Updated heart rate: {current_heart_rate}")
                    except json.JSONDecodeError:
                        print(f"Invalid JSON: {line}")
    except serial.SerialException as e:
        print(f"Serial error: {e}")


class SineWaveTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, get_bpm_callback, sample_rate=48000):
        super().__init__()
        self.sample_rate = sample_rate
        self.get_bpm = get_bpm_callback
        self.time = 0.0

    async def recv(self):
        bpm = self.get_bpm()
        freq = bpm / 60.0  # Convert BPM to Hz
        samples = 960  # 20ms of audio at 48kHz
        t = np.arange(samples) / self.sample_rate + self.time
        self.time += samples / self.sample_rate

        # Generate sine wave, low volume
        wave = 0.2 * np.sin(2 * np.pi * freq * t).astype(np.float32)

        # Create audio frame
        frame = AudioFrame(format="flt", layout="mono", samples=samples)
        frame.planes[0].update(wave.tobytes())
        frame.sample_rate = self.sample_rate
        return frame


async def connect_websocket():
    uri = "ws://localhost:8080"  # Replace with your server IP/port
    return await websockets.connect(uri)


async def run():
    pc = RTCPeerConnection()
    ws = await connect_websocket()
    print("Connected to signaling server.")

    # Heartbeat audio track
    audio_track = SineWaveTrack(lambda: current_heart_rate)
    pc.addTrack(audio_track)

    answer_received = False

    @pc.on("icecandidate")
    async def on_icecandidate(event):
        if event.candidate:
            await ws.send(json.dumps({
                "type": "candidate",
                "candidate": {
                    "candidate": event.candidate.candidate,
                    "sdpMid": event.candidate.sdpMid,
                    "sdpMLineIndex": event.candidate.sdpMLineIndex
                }
            }))

    # Send offer
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    await ws.send(json.dumps({
        "type": pc.localDescription.type,
        "sdp": pc.localDescription.sdp
    }))

    try:
        async for message in ws:
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            data = json.loads(message)

            if data.get("type") == "answer":
                if not answer_received:
                    print("Received answer.")
                    await pc.setRemoteDescription(RTCSessionDescription(
                        sdp=data["sdp"],
                        type=data["type"]
                    ))
                    answer_received = True
            elif data.get("type") == "candidate":
                c = data["candidate"]
                candidate = RTCIceCandidate(
                    candidate=c["candidate"],
                    sdpMid=c["sdpMid"],
                    sdpMLineIndex=c["sdpMLineIndex"]
                )
                await pc.addIceCandidate(candidate)

    except Exception as e:
        print(f"Signaling error: {e}")
    finally:
        await ws.close()
        await pc.close()


if __name__ == "__main__":
    # Start serial thread for live heart rate data
    threading.Thread(target=read_serial, daemon=True).start()
    # Start WebRTC audio streaming
    asyncio.run(run())
