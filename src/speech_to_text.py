"""Reconhecimento de fala local com faster-whisper."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

import numpy as np

from src.debug_log import log

WHISPER_MODELS = ["tiny", "base", "small", "medium"]
COMPUTE_OPTIONS = ["cpu", "auto", "cuda"]
TRANSCRIBE_TIMEOUT = 30
SAMPLE_RATE = 16000


def detect_compute_device(preference: str = "cpu") -> str:
    """Resolve dispositivo de inferência. 'auto' tenta CUDA com fallback para CPU."""
    if preference == "cpu":
        return "cpu"
    if preference == "cuda":
        return "cuda"
    # auto: tenta CUDA, mas load() faz fallback se DLL/driver faltar
    try:
        import ctranslate2

        if ctranslate2.get_supported_compute_types("cuda"):
            return "cuda"
    except Exception:
        pass
    return "cpu"


class SpeechToText:
    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        language: str | None = None,
    ):
        self.model_size = model_size
        self._preference = device
        self.device = detect_compute_device(device)
        self.language = None if language in (None, "", "auto") else language
        self._model = None

    def load(self):
        if self._model is not None:
            return

        from faster_whisper import WhisperModel

        candidates = []
        if self._preference == "cpu":
            candidates = ["cpu"]
        elif self._preference == "cuda":
            candidates = ["cuda", "cpu"]
        else:
            candidates = ["cuda", "cpu"]

        last_error = None
        for dev in candidates:
            compute_type = "int8" if dev == "cpu" else "float16"
            try:
                log(f"Carregando Whisper '{self.model_size}' em {dev.upper()}...")
                self._model = WhisperModel(
                    self.model_size,
                    device=dev,
                    compute_type=compute_type,
                )
                if dev == "cuda":
                    self._verify_cuda()
                self.device = dev
                log(f"Whisper pronto ({dev.upper()}).")
                return
            except Exception as exc:
                last_error = exc
                log(f"Falha em {dev.upper()}: {exc}")
                self._model = None

        raise RuntimeError(
            f"Não foi possível carregar o Whisper. Último erro: {last_error}"
        )

    def _verify_cuda(self):
        """Testa se CUDA funciona de verdade (cublas etc.)."""
        probe = np.zeros(SAMPLE_RATE, dtype=np.float32)
        segs, _ = self._model.transcribe(probe, beam_size=1)
        list(segs)

    def _fallback_to_cpu(self):
        if self.device == "cpu":
            return
        log("CUDA indisponível — trocando para CPU...")
        self._model = None
        self.device = "cpu"
        self._preference = "cpu"
        self.load()

    def _transcribe_inner(self, audio: np.ndarray) -> str:
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        segments, info = self._model.transcribe(
            audio,
            language=self.language,
            vad_filter=False,
            beam_size=1,
            condition_on_previous_text=False,
            temperature=0.0,
        )
        parts = [seg.text.strip() for seg in segments if seg.text.strip()]
        detected = getattr(info, "language", None)
        text = " ".join(parts)
        log(f"STT: {len(audio)/16000:.1f}s → '{text[:80]}' (lang={detected})")
        return text

    def transcribe(self, audio: np.ndarray) -> str:
        self.load()
        duration = len(audio) / 16000
        log(f"Transcrevendo {duration:.1f}s de áudio ({self.device.upper()})...")

        for attempt in range(2):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self._transcribe_inner, audio)
                try:
                    return future.result(timeout=TRANSCRIBE_TIMEOUT)
                except FuturesTimeout:
                    log(f"STT timeout após {TRANSCRIBE_TIMEOUT}s")
                    if self.device == "cuda" and attempt == 0:
                        self._fallback_to_cpu()
                        continue
                    raise TimeoutError(
                        f"Transcrição demorou mais de {TRANSCRIBE_TIMEOUT}s. "
                        "Use o modelo 'tiny' em Processamento: CPU."
                    )
                except Exception as exc:
                    err = str(exc).lower()
                    if self.device == "cuda" and attempt == 0 and (
                        "cublas" in err or "cuda" in err or "dll" in err
                    ):
                        self._fallback_to_cpu()
                        continue
                    raise

        return ""
