import os
import time
import re
import threading
import struct
import speech_recognition as sr
import asyncio
import edge_tts
import pygame
import tempfile

# Optional webrtcvad — gracefully degrade if not installed
try:
    import webrtcvad
    _VAD_AVAILABLE = True
except ImportError:
    _VAD_AVAILABLE = False
    print("webrtcvad not found — VAD pre-filter disabled. Run: pip install webrtcvad")

class VoiceInterface:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        
        # Initialize pygame mixer for audio playback
        pygame.mixer.init()
        
        # TTS voices per language
        self.voice_en = "en-US-AvaNeural"     # Natural American female
        self.voice_ml = "ml-IN-SobhanaNeural"  # Malayalam female
        
        # We need a lock for engine speak to avoid threading issues
        self.engine_lock = threading.Lock()
        self._speaking = False
        self.temp_dir = tempfile.gettempdir()

    def stop_speaking(self):
        """Stops any ongoing audio playback."""
        if self._speaking:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            self._speaking = False

    def _init_microphone(self):
        # Initialize microphone only when needed to avoid issues on some systems
        try:
            return sr.Microphone()
        except Exception as e:
            print(f"Microphone init error: {e}")
            return None

    def listen(self):
        """Listens for audio and converts it to text.
        
        When webrtcvad is available, applies a voice-activity pre-filter to
        skip silent recordings before sending to the speech recognizer. This
        avoids wasted STT API calls and speeds up the listen-loop significantly.
        """
        mic = self._init_microphone()
        if not mic:
            return None

        with mic as source:
            print("Listening...")
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
            except sr.WaitTimeoutError:
                return None

        # ── WebRTC VAD pre-filter ─────────────────────────────────────────────
        if _VAD_AVAILABLE:
            try:
                vad = webrtcvad.Vad(2)  # Aggressiveness 0-3; 2 = balanced
                raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
                # Split raw PCM into 20ms frames (16000 Hz × 2 bytes × 0.02s = 640 bytes)
                frame_size = 640
                frames = [raw[i:i + frame_size] for i in range(0, len(raw) - frame_size, frame_size)]
                speech_frames = sum(1 for f in frames if len(f) == frame_size and vad.is_speech(f, 16000))
                speech_ratio = speech_frames / max(len(frames), 1)
                if speech_ratio < 0.10:
                    # Less than 10% of frames contain speech — skip STT call
                    print("VAD: no speech detected, skipping recognition.")
                    return None
            except Exception as vad_err:
                print(f"VAD error (ignored): {vad_err}")

        # ── Speech recognition ────────────────────────────────────────────────
        try:
            print("Recognizing...")
            text = self.recognizer.recognize_google(audio)
            print(f"You said: {text}")
            return text
        except sr.UnknownValueError:
            print("Could not understand audio")
            return None
        except sr.RequestError as e:
            print(f"STT request error: {e}")
            return None

    def _detect_language(self, text):
        """Returns 'ml' if text contains Malayalam script, else 'en'."""
        malayalam_count = sum(1 for ch in text if '\u0D00' <= ch <= '\u0D7F')
        return 'ml' if malayalam_count > len(text) * 0.2 else 'en'

    async def _generate_speech(self, text, output_file):
        lang = self._detect_language(text)
        voice = self.voice_ml if lang == 'ml' else self.voice_en
        rate = "-10%" if lang == 'en' else "+0%"
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(output_file)

    def speak(self, text):
        """Converts text to speech using Edge TTS and plays it."""
        if not text:
            return

        # Filter out gesture tags inside [brackets]
        speech_text = re.sub(r'\[.*?\]', '', text).strip()
        if not speech_text:
            return

        print(f"Speaking: {speech_text}")
        
        with self.engine_lock:
            self._speaking = True
            temp_file = os.path.join(self.temp_dir, f"speech_{int(time.time())}.mp3")
            
            try:
                # Generate audio file asynchronously
                asyncio.run(self._generate_speech(speech_text, temp_file))
                
                # Play audio using pygame
                pygame.mixer.music.load(temp_file)
                pygame.mixer.music.play()
                
                # Wait for playback to finish
                while pygame.mixer.music.get_busy():
                    if not self._speaking: # Check if stop_speaking was called
                        pygame.mixer.music.stop()
                        break
                    time.sleep(0.1)
                
                pygame.mixer.music.unload()
            except Exception as e:
                print(f"TTS Error: {e}")
            finally:
                self._speaking = False
                # Cleanup temp file
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass

    def listen_quick(self, timeout=1.5):
        """Fast listen with short timeout — for interruption detection during speech."""
        mic = self._init_microphone()
        if not mic:
            return None

        with mic as source:
            try:
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=5)
            except sr.WaitTimeoutError:
                return None

        # Quick VAD check
        if _VAD_AVAILABLE:
            try:
                vad = webrtcvad.Vad(2)
                raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
                frame_size = 640
                frames = [raw[i:i + frame_size] for i in range(0, len(raw) - frame_size, frame_size)]
                speech_frames = sum(1 for f in frames if len(f) == frame_size and vad.is_speech(f, 16000))
                if speech_frames / max(len(frames), 1) < 0.10:
                    return None
            except Exception:
                pass

        try:
            return self.recognizer.recognize_google(audio)
        except (sr.UnknownValueError, sr.RequestError):
            return None

    def speak_async(self, text):
        """Non-blocking speak — runs TTS in background thread.
        Returns the thread so caller can join if needed."""
        t = threading.Thread(target=self.speak, args=(text,), daemon=True)
        t.start()
        return t

    def is_speaking(self):
        """Check if audio is currently playing."""
        return self._speaking

if __name__ == "__main__":
    # Test script
    vi = VoiceInterface()
    text = vi.listen()
    if text:
        vi.speak(f"I heard you say: {text}")
    else:
        vi.speak("I didn't catch that.")
