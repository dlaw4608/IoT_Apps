import asyncio
import json
import numpy as np
import fractions
import websockets

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate, MediaStreamTrack
from av import AudioFrame

class SineWaveTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, frequency=440.0, sample_rate=48000):
        super().__init__()
        self.frequency = frequency
        self.sample_rate = sample_rate
        self.time = 0.0

    async def recv(self):
        samples = 960  # 20ms of audio at 48kHz
        t = np.arange(samples) / self.sample_rate + self.time
        self.time += samples / self.sample_rate

        # Generate sine wave (scaled to int16)
        wave = (0.2 * np.sin(2 * np.pi * self.frequency * t) * 32767).astype(np.int16)

        # Create audio frame
        frame = AudioFrame(format="s16", layout="mono", samples=samples)
        frame.planes[0].update(wave.tobytes())
        frame.sample_rate = self.sample_rate

        # Set timing metadata
        frame.pts = int(self.time * self.sample_rate)
        frame.time_base = fractions.Fraction(1, self.sample_rate)

        print(f"→ Sending frame @ t={self.time:.3f}s")

        # Simulate real-time pacing
        await asyncio.sleep(0.02)
        return frame

async def connect_websocket():
    uri = "ws://54.216.122.197:8080"  # Replace if needed
    return await websockets.connect(uri)

async def run():
    pc = RTCPeerConnection()
    ws = await connect_websocket()
    print("[+] WebSocket connected")

    audio_track = SineWaveTrack()
    pc.addTrack(audio_track)
    print("[+] Sine wave track added")

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
            print("[>] Sent ICE candidate")

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    print("[>] Sent offer")
    await ws.send(json.dumps({
        "type": pc.localDescription.type,
        "sdp": pc.localDescription.sdp
    }))

    try:
        async for message in ws:
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            data = json.loads(message)

            if data.get("type") == "answer" and not answer_received:
                print("[<] Got SDP answer")
                await pc.setRemoteDescription(RTCSessionDescription(
                    sdp=data["sdp"],
                    type=data["type"]
                ))
                answer_received = True

            elif data.get("type") == "candidate":
                c = data["candidate"]
                await pc.addIceCandidate(RTCIceCandidate(
                    candidate=c["candidate"],
                    sdpMid=c["sdpMid"],
                    sdpMLineIndex=c["sdpMLineIndex"]
                ))
                print("[<] Got ICE candidate")

    except Exception as e:
        print(f"[!] Error: {e}")
    finally:
        print("[*] Closing...")
        await ws.close()
        await pc.close()

if __name__ == "__main__":
    asyncio.run(run())
