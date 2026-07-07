"""Pipeline áudio → VAD → STT → tradução para legendas em tempo real."""

import queue
import threading
import time

from src.audio_capture import AudioCapture, SAMPLE_RATE
from src.audio_sources import create_audio_capture
from src.debug_log import log
from src.speech_to_text import SpeechToText
from src.translator import Translator
from src.vad_processor import VADProcessor


class AudioPipeline:
    def __init__(
        self,
        translator: Translator,
        device: str | None = None,
        capture_mode: str = "system",
        target_pid: int | None = None,
        whisper_model: str = "base",
        compute_device: str = "auto",
        source_language: str = "auto",
        streaming: bool = True,
        on_status=None,
        on_original=None,
        on_translation=None,
        on_translation_partial=None,
        on_error=None,
    ):
        self.translator = translator
        self.device = device
        self.capture_mode = capture_mode
        self.target_pid = target_pid
        self.whisper_model = whisper_model
        self.compute_device = compute_device
        self.source_language = source_language
        self.streaming = streaming
        self.on_status = on_status or (lambda _msg: None)
        self.on_original = on_original or (lambda _text: None)
        self.on_translation = on_translation or (lambda _text: None)
        self.on_translation_partial = on_translation_partial or (lambda _text: None)
        self.on_error = on_error or (lambda _err: None)

        self._capture: AudioCapture | None = None
        self._vad: VADProcessor | None = None
        self._stt: SpeechToText | None = None
        self._running = False
        self._capture_thread: threading.Thread | None = None
        self._worker_thread: threading.Thread | None = None
        self._segment_queue: queue.Queue = queue.Queue(maxsize=4)
        self._last_translation = ""

    def start(self):
        if self._running:
            return
        self.on_status("Carregando modelo de voz...")
        self._stt = SpeechToText(
            model_size=self.whisper_model,
            device=self.compute_device,
            language=self.source_language,
        )
        self._stt.load()

        self.on_status("Carregando detecção de voz (VAD)...")
        self._vad = VADProcessor(max_speech_duration=6.0)
        self._vad.warmup()

        self._capture = create_audio_capture(
            mode=self.capture_mode,
            device=self.device,
            target_pid=self.target_pid,
        )
        self._running = True
        self._capture.start()
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._capture_thread.start()
        self._worker_thread.start()
        device_label = self._stt.device.upper()
        source_label = "APP" if self.capture_mode == "application" else device_label
        self.on_status(f"Ouvindo áudio ({source_label})...")
        log(f"Pipeline iniciado ({self.capture_mode}, {source_label})")

    def stop(self):
        self._running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=3)
            self._capture_thread = None
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
            self._worker_thread = None
        if self._capture:
            self._capture.close()
            self._capture = None
        self._vad = None
        self._stt = None
        self._last_translation = ""
        while not self._segment_queue.empty():
            try:
                self._segment_queue.get_nowait()
            except queue.Empty:
                break
        self.on_status("Parado")
        log("Pipeline parado.")

    def _translate(self, text: str):
        log(f"Traduzindo: '{text[:80]}'")
        if self.streaming:
            def _on_partial(partial: str):
                if partial:
                    self.on_translation_partial(partial)

            translation = self.translator.translate_text_stream(
                text, on_delta=_on_partial,
            )
        else:
            translation = self.translator.translate_text(text)

        if translation and translation != self._last_translation:
            self._last_translation = translation
            self.on_translation(translation)
            log(f"Tradução: '{translation[:80]}'")

    def _capture_loop(self):
        while self._running:
            try:
                chunk = self._capture.get_chunk(timeout=0.2)
                if chunk is None:
                    continue
                segment = self._vad.process_chunk(chunk)
                if segment is None:
                    continue
                duration = len(segment) / SAMPLE_RATE
                log(f"Segmento de fala: {duration:.1f}s")
                try:
                    self._segment_queue.put_nowait(segment)
                except queue.Full:
                    log("Fila cheia — descartando segmento antigo")
                    try:
                        self._segment_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self._segment_queue.put_nowait(segment)
            except Exception as exc:
                log(f"Erro captura: {exc}")
                self.on_error(str(exc))

    def _worker_loop(self):
        device_label = lambda: self._stt.device.upper() if self._stt else "CPU"
        while self._running:
            try:
                try:
                    segment = self._segment_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                duration = len(segment) / SAMPLE_RATE
                self.on_status(f"Transcrevendo ({duration:.1f}s)...")
                t0 = time.time()

                text = self._stt.transcribe(segment)
                elapsed = time.time() - t0
                log(f"Transcrição levou {elapsed:.1f}s")

                if not text:
                    self.on_status(f"Ouvindo áudio ({device_label()})...")
                    continue

                self.on_original(text)
                self.on_status("Traduzindo...")
                self._translate(text)
                self.on_status(f"Ouvindo áudio ({device_label()})...")
            except Exception as exc:
                log(f"Erro worker: {exc}")
                self.on_error(str(exc))
                self.on_status(f"Erro: {str(exc)[:60]}")
