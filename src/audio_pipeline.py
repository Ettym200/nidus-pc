"""Pipeline áudio → VAD → STT → tradução para legendas em tempo real."""

import queue
import threading
import time

from src.audio_capture import AudioCapture, SAMPLE_RATE
from src.audio_sources import create_audio_capture
from src.debug_log import log
from src.text_sanitize import sanitize_display_text
from src.interview_buffer import InterviewQuestionBuffer
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
        mode: str = "translate",
        interview_context: str = "",
        interview_type: str = "Geral",
        answer_language: str = "Português",
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
        self.mode = mode
        self.interview_context = interview_context
        self.interview_type = interview_type
        self.answer_language = answer_language
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
        self._last_output = ""
        self._last_answered_question = ""
        self._last_transcript = ""
        self._question_buffer: InterviewQuestionBuffer | None = None
        self._answer_generation = 0
        self._answer_lock = threading.Lock()

    def _vad_for_mode(self) -> VADProcessor:
        if self.mode == "interview":
            return VADProcessor(
                max_speech_duration=45.0,
                silence_duration=1.8,
                min_speech_duration=0.6,
            )
        return VADProcessor(max_speech_duration=12.0, silence_duration=0.7)

    def _init_question_buffer(self):
        self._question_buffer = InterviewQuestionBuffer(
            pause_seconds=2.2,
            on_update=lambda text: self.on_original(text),
            on_complete=self._on_interview_question_complete,
        )

    def _on_interview_question_complete(self, question: str):
        if not question or question == self._last_answered_question:
            return
        self._last_answered_question = question
        self.on_original(question)
        self.on_status("Gerando resposta...")
        threading.Thread(
            target=self._suggest_answer,
            args=(question,),
            daemon=True,
        ).start()

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
        self._vad = self._vad_for_mode()
        self._vad.warmup()
        if self.mode == "interview":
            self._init_question_buffer()
            log("Modo entrevista: VAD longo + buffer de pergunta (2.2s pausa)")

        self._capture = create_audio_capture(
            mode=self.capture_mode,
            device=self.device,
            target_pid=self.target_pid,
        )
        self._running = True
        try:
            self._capture.start()
        except Exception as exc:
            self._running = False
            self._capture = None
            log(f"Erro ao iniciar captura: {exc}")
            raise RuntimeError(f"Falha na captura de áudio: {exc}") from exc
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
        self._last_output = ""
        self._last_answered_question = ""
        self._last_transcript = ""
        if self._question_buffer:
            self._question_buffer.clear()
        self._question_buffer = None
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
                cleaned = sanitize_display_text(partial)
                if cleaned:
                    self.on_translation_partial(cleaned)

            translation = self.translator.translate_text_stream(
                text, on_delta=_on_partial,
            )
        else:
            translation = self.translator.translate_text(text)

        if translation and translation != self._last_output:
            translation = sanitize_display_text(translation)
            if not translation:
                return
            self._last_output = translation
            self.on_translation(translation)
            log(f"Tradução: '{translation[:80]}'")

    def _suggest_answer(self, question: str):
        with self._answer_lock:
            self._answer_generation += 1
            gen_id = self._answer_generation

        log(f"Gerando resposta para: '{question[:120]}'")
        if self.streaming:
            def _on_partial(partial: str):
                if partial and gen_id == self._answer_generation:
                    self.on_translation_partial(partial)

            answer = self.translator.suggest_interview_answer(
                question,
                answer_language=self.answer_language,
                context=self.interview_context,
                interview_type=self.interview_type,
                on_delta=_on_partial,
            )
        else:
            answer = self.translator.suggest_interview_answer(
                question,
                answer_language=self.answer_language,
                context=self.interview_context,
                interview_type=self.interview_type,
            )

        if gen_id != self._answer_generation:
            log("Resposta descartada — entrevistador continuou falando")
            return

        if answer and answer != self._last_output:
            self._last_output = answer
            self.on_translation(answer)
            log(f"Resposta sugerida: '{answer[:80]}'")

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

                if self.mode == "interview":
                    with self._answer_lock:
                        self._answer_generation += 1
                    if self._question_buffer:
                        self._question_buffer.add_fragment(text)
                    self.on_status("Ouvindo pergunta...")
                    continue

                if text == self._last_transcript:
                    self.on_status(f"Ouvindo áudio ({device_label()})...")
                    continue
                self._last_transcript = text

                self.on_original(text)
                self.on_status("Traduzindo...")
                self._translate(text)
                self.on_status(f"Ouvindo áudio ({device_label()})...")
            except Exception as exc:
                import traceback
                log(f"Erro worker: {exc}\n{traceback.format_exc()}")
                self.on_error(str(exc))
                self.on_status(f"Erro: {str(exc)[:60]}")
