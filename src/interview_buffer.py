"""Acumula fragmentos de transcrição até o entrevistador terminar de falar."""

from __future__ import annotations

import re
import threading


class InterviewQuestionBuffer:
    """Junta trechos de fala e só emite a pergunta completa após uma pausa."""

    def __init__(
        self,
        pause_seconds: float = 2.2,
        on_update=None,
        on_complete=None,
    ):
        self.pause_seconds = pause_seconds
        self.on_update = on_update or (lambda _text: None)
        self.on_complete = on_complete or (lambda _text: None)
        self._parts: list[str] = []
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def _merged(self) -> str:
        return " ".join(p.strip() for p in self._parts if p.strip()).strip()

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip())

    def _merge_fragment(self, text: str):
        text = self._normalize(text)
        if not text:
            return
        if not self._parts:
            self._parts.append(text)
            return
        last = self._parts[-1]
        if text == last or text in last:
            return
        if last in text:
            self._parts[-1] = text
            return
        self._parts.append(text)

    def _arm_timer(self):
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(self.pause_seconds, self._on_pause)
        self._timer.daemon = True
        self._timer.start()

    def _on_pause(self):
        with self._lock:
            merged = self._merged()
            self._parts = []
            self._timer = None
        if merged:
            self.on_complete(merged)

    def add_fragment(self, text: str):
        with self._lock:
            self._merge_fragment(text)
            merged = self._merged()
            if merged:
                self.on_update(merged)
            self._arm_timer()

    def flush(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            merged = self._merged()
            self._parts = []
        if merged:
            self.on_complete(merged)

    def clear(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            self._parts = []
