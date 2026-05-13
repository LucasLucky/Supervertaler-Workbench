"""
ISO 639-1 / BCP-47 language code ↔ English-name mapping.

Used by bilingual-DOCX / RTF handlers to translate the language codes
they extract from file metadata (e.g. Phrase's ``Source (cs) | Target
(de-de)`` header) into the English names Workbench's language pickers
display (``Czech``, ``German``).

Covers the languages in the New-Project dialog's
``available_languages`` list (full Workbench picker set). Codes are
matched case-insensitively against the 2-letter ISO 639-1 prefix, so
inputs like ``cs``, ``cs-CZ``, ``cs-cz``, ``CS-CZ`` all resolve to
``Czech``.

If you add a language to the New-Project picker, also add it here so
the auto-detection round-trips cleanly. Unknown codes return ``None``
and the caller falls back to whatever it does for "couldn't
auto-detect".
"""

from __future__ import annotations

from typing import Optional


# ISO 639-1 → English language name. Keep this in sync with the
# ``available_languages`` list in Supervertaler.py's new-project and
# Phrase / Trados import dialogs.
_ISO_TO_ENGLISH: dict[str, str] = {
    "af": "Afrikaans",
    "ar": "Arabic",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "ca": "Catalan",
    "cs": "Czech",
    "cy": "Welsh",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "et": "Estonian",
    "eu": "Basque",
    "fa": "Persian",
    "fi": "Finnish",
    "fr": "French",
    "ga": "Irish",
    "gl": "Galician",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "hy": "Armenian",
    "id": "Indonesian",
    "is": "Icelandic",
    "it": "Italian",
    "ja": "Japanese",
    "ka": "Georgian",
    "ko": "Korean",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mk": "Macedonian",
    "ms": "Malay",
    "nl": "Dutch",
    "no": "Norwegian",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sq": "Albanian",
    "sr": "Serbian",
    "sv": "Swedish",
    "sw": "Swahili",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "vi": "Vietnamese",
    "zh": "Chinese (Simplified)",  # see note below re: Hans/Hant
}

# Subtags that mean "Traditional Chinese" – when present we prefer the
# Traditional variant in the picker. Phrase / Trados both occasionally
# emit ``zh-TW`` or ``zh-HK`` for Traditional and ``zh-CN`` for
# Simplified, so we honour that distinction.
_ZH_TRADITIONAL_REGIONS = {"tw", "hk", "mo", "hant"}


def iso_to_english_name(code: Optional[str]) -> Optional[str]:
    """Resolve a BCP-47 / ISO 639-1 code to Workbench's English name.

    Args:
        code: A language code like ``"cs"``, ``"cs-CZ"``, ``"de-de"``,
            ``"zh-Hant"``. Whitespace and case are tolerated. ``None``
            or an unknown code returns ``None``.

    Returns:
        The English language name as Workbench's pickers spell it
        (``"Czech"``, ``"German"``, ``"Chinese (Traditional)"``), or
        ``None`` if the code isn't recognised.
    """
    if not code:
        return None
    s = str(code).strip().lower()
    if not s:
        return None
    # Split off the region / script tag (``cs-CZ`` → ``cs``,
    # ``zh-Hant`` → primary ``zh`` + tag ``hant``).
    if "-" in s:
        primary, region = s.split("-", 1)
        # Disambiguate Chinese variants.
        if primary == "zh" and region.split("-")[0] in _ZH_TRADITIONAL_REGIONS:
            return "Chinese (Traditional)"
    else:
        primary = s
    return _ISO_TO_ENGLISH.get(primary)
