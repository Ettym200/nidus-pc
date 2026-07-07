"""Filtra alucinações e repetições comuns do Whisper e da tradução."""

from __future__ import annotations

import re
from collections import Counter

FILLER_WORDS = {
    "hum", "uhum", "uh", "um", "ah", "hmm", "mhm", "hm", "aham", "ahn",
    "uh-huh", "uhh", "umm", "hã", "ham", "hem",
}

HALLUCINATION_PHRASES = (
    "obrigado por assistir",
    "thanks for watching",
    "thank you for watching",
    "inscreva-se",
    "subscribe",
    "legendas",
    "subtitle",
    "amara.org",
    "fonte de som",
    "som mudo",
    "mute the boy",
    "audience applauds",
    "applause",
)


def _normalize_token(word: str) -> str:
    return re.sub(r"[^\w'-]", "", word.lower())


def _repetition_ratio(words: list[str]) -> float:
    if len(words) < 4:
        return 0.0
    counts = Counter(_normalize_token(w) for w in words if _normalize_token(w))
    if not counts:
        return 0.0
    return counts.most_common(1)[0][1] / len(words)


def _collapse_consecutive(words: list[str], max_repeat: int = 2) -> list[str]:
    if not words:
        return []
    out: list[str] = []
    prev_norm = ""
    streak = 0
    for word in words:
        norm = _normalize_token(word)
        if norm and norm == prev_norm:
            streak += 1
            if streak <= max_repeat:
                out.append(word)
        else:
            prev_norm = norm
            streak = 1
            out.append(word)
    return out


def _is_filler_only(text: str) -> bool:
    words = [_normalize_token(w) for w in text.split()]
    words = [w for w in words if w]
    return bool(words) and all(w in FILLER_WORDS for w in words)


def sanitize_speech_text(text: str) -> str:
    """Limpa transcrição STT antes de traduzir ou exibir."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ""

    lower = text.lower()
    for phrase in HALLUCINATION_PHRASES:
        if phrase in lower:
            return ""

    words = text.split()
    if _repetition_ratio(words) >= 0.55:
        collapsed = _collapse_consecutive(words, max_repeat=2)
        text = " ".join(collapsed)
        if _repetition_ratio(text.split()) >= 0.55 and not _is_filler_only(text):
            return ""
        words = text.split()

    words = _collapse_consecutive(words, max_repeat=2)
    text = " ".join(words).strip()

    if _is_filler_only(text):
        uniq = text.split()[:2]
        return " ".join(uniq)

    if len(text) > 280 and _repetition_ratio(text.split()) >= 0.35:
        return ""

    return text


def sanitize_display_text(text: str, max_len: int = 320) -> str:
    """Última camada antes do overlay — evita blocos gigantes repetidos."""
    text = sanitize_speech_text(text)
    if not text:
        return ""
    if len(text) > max_len:
        text = text[: max_len - 3].rstrip() + "..."
    return text
