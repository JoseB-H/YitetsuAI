from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from spellchecker import SpellChecker


COMMON_CORRECTIONS = {
    "qiero": "quiero",
    "kiero": "quiero",
    "aser": "hacer",
    "aserlo": "hacerlo",
    "grasias": "gracias",
    "grasia": "gracias",
    "aplicasion": "aplicación",
    "aplicaciones": "aplicaciones",
    "desarollo": "desarrollo",
    "desarollar": "desarrollar",
    "desarollador": "desarrollador",
    "proyeto": "proyecto",
    "pajina": "página",
    "pajinas": "páginas",
    "informasion": "información",
    "conversasion": "conversación",
    "conversasiones": "conversaciones",
    "inteligensia": "inteligencia",
    "artifisial": "artificial",
    "organizasion": "organización",
    "nesesito": "necesito",
    "nesesita": "necesita",
    "nesesitamos": "necesitamos",
    "alluda": "ayuda",
    "ayudame": "ayúdame",
    "ke": "que",
    "recieve": "receive",
    "enviroment": "environment",
    "teh": "the",
    "adn": "and",
    "definately": "definitely",
    "seperate": "separate",
    "occured": "occurred",
}

DOMAIN_WORDS = {
    "yitetsuai",
    "yitetsu",
    "api",
    "apis",
    "fastapi",
    "postgresql",
    "postgres",
    "pgvector",
    "ollama",
    "llm",
    "llms",
    "ia",
    "ai",
    "typescript",
    "javascript",
    "react",
    "frontend",
    "backend",
    "sql",
    "rag",
}

TOKEN_PATTERN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?", re.UNICODE)
SPELL_CHECKERS = (SpellChecker(language="es"), SpellChecker(language="en"))
for checker in SPELL_CHECKERS:
    checker.word_frequency.load_words(DOMAIN_WORDS)


@dataclass(frozen=True)
class PromptInterpretation:
    original: str
    interpreted: str
    corrections: tuple[tuple[str, str], ...]

    @property
    def was_corrected(self) -> bool:
        return bool(self.corrections)


def _match_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _suggest_correction(word: str) -> str | None:
    lowered = word.lower()
    mapped = COMMON_CORRECTIONS.get(lowered)
    if mapped is not None:
        return _match_case(word, mapped)

    unaccented = "".join(
        character
        for character in unicodedata.normalize("NFD", lowered)
        if unicodedata.category(character) != "Mn"
    )
    if any(
        candidate in checker
        for checker in SPELL_CHECKERS
        for candidate in (lowered, unaccented)
    ):
        return None

    candidates: set[str] = set()
    for checker in SPELL_CHECKERS:
        candidates.update(checker.candidates(lowered) or ())

    # Avoid changing an unfamiliar name or a word with multiple plausible meanings.
    if len(candidates) != 1:
        return None
    candidate = candidates.pop()
    if len(candidate) < 3 or candidate.lower() == lowered:
        return None
    if not all(character.isascii() for character in lowered) and not all(
        character.isascii() for character in candidate
    ):
        return None
    return _match_case(word, candidate)


def interpret_prompt(prompt: str) -> PromptInterpretation:
    corrections: list[tuple[str, str]] = []

    def replace_word(match: re.Match[str]) -> str:
        original = match.group(0)
        corrected = _suggest_correction(original)
        if corrected is None or corrected.lower() == original.lower():
            return original
        corrections.append((original, corrected))
        return corrected

    interpreted = TOKEN_PATTERN.sub(replace_word, prompt)
    return PromptInterpretation(
        original=prompt,
        interpreted=interpreted,
        corrections=tuple(corrections),
    )
