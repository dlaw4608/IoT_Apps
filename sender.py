import asyncio
import json
import time
import websockets
import av

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc.mediastreams import AudioStreamTrack


class AudioFileTrack(AudioStreamTrack):
    """
    A MediaStreamTrack that reads and streams audio from a file using PyAV,
    with real-time pacing based on timestamps.
    """
    def __init__(self, path):
        super().__init__()  # Initialize as audio track
        self.container = av.open(path)
        self.stream = self.container.streams.audio[0]
        self.frames = self.container.decode(self.stream)
        self.start_time = None

    async def recv(self):
        frame = next(self.frames, None)
        if frame is None:
            print("End of audio stream.")
            raise asyncio.CancelledError("No more audio frames")

        if self.start_time is None:
            self.start_time = time.time()

        # Pace the frames according to their timestamp
        now = time.time()
        expected_play_time = self.start_time + frame.time
        delay = expected_play_time - now
        if delay > 0:
            await asyncio.sleep(delay)

        return frame


async def connect_websocket():
    uri = "ws://localhost:8080"
    return await websockets.connect(uri)


async def run():
    print("Connecting to signaling server...")
    pc = RTCPeerConnection()
    ws = await connect_websocket()
    print("Connected to signaling server.")

    # Add the audio track
    audio_path = '/Users/daniellawton/Documents/IoT_Lock_In/audio/12_DARE_48k.wav'  # Change to your file
    audio_track = AudioFileTrack(audio_path)
    pc.addTrack(audio_track)
    print("Audio track added.")

    @pc.on("icecandidate")
    async def on_icecandidate(event):
        if event.candidate:
            candidate_dict = {
                "type": "candidate",
                "candidate": {
                    "candidate": event.candidate.candidate,
                    "sdpMid": event.candidate.sdpMid,
                    "sdpMLineIndex": event.candidate.sdpMLineIndex
                }
            }
            await ws.send(json.dumps(candidate_dict))
            print("Sent ICE candidate.")

    # Create offer
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    print("Sending offer...")
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
                print("Received SDP answer.")
                await pc.setRemoteDescription(RTCSessionDescription(
                    sdp=data["sdp"],
                    type=data["type"]
                ))

            elif data.get("type") == "candidate":
                candidate_info = data["candidate"]
                candidate = RTCIceCandidate(
                    candidate=candidate_info["candidate"],
                    sdpMid=candidate_info["sdpMid"],
                    sdpMLineIndex=candidate_info["sdpMLineIndex"]
                )
                await pc.addIceCandidate(candidate)
                print("Added ICE candidate from receiver.")

    except Exception as e:
        print(f"Error during signaling: {e}")
    finally:
        print("Cleaning up...")
        await ws.close()
        await pc.close()

# Run the sender
if __name__ == "__main__":
    asyncio.run(run())
