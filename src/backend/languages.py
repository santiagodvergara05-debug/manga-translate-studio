"""
Language definitions, locale metadata, and comic sound effects (SFX) adaptation rules.

This module provides the central repository for supported source/target languages
and generates localized prompt directives for onomatopoeia translation.
"""

# Supported source languages for OCR/multimodal extraction
SUPPORTED_SOURCE_LANGUAGES = [
    {"code": "en", "name": "English", "native": "English"},
    {"code": "ko", "name": "Korean", "native": "한국어"},
    {"code": "ja", "name": "Japanese", "native": "日本語"},
    {"code": "zh", "name": "Chinese", "native": "中文"},
    {"code": "es", "name": "Spanish", "native": "Español"},
    {"code": "fr", "name": "French", "native": "Français"},
    {"code": "de", "name": "German", "native": "Deutsch"},
    {"code": "it", "name": "Italian", "native": "Italiano"},
    {"code": "pt", "name": "Portuguese", "native": "Português"},
    {"code": "ru", "name": "Russian", "native": "Русский"},
    {"code": "id", "name": "Indonesian", "native": "Bahasa Indonesia"},
    {"code": "th", "name": "Thai", "native": "ไทย"},
    {"code": "vi", "name": "Vietnamese", "native": "Tiếng Việt"},
    {"code": "tr", "name": "Turkish", "native": "Türkçe"},
    {"code": "pl", "name": "Polish", "native": "Polski"},
]

# Supported target scanlation languages
SUPPORTED_TARGET_LANGUAGES = [
    {"code": "es", "name": "Spanish (Neutral)", "native": "Español Neutro"},
    {"code": "en", "name": "English", "native": "English"},
    {"code": "pt-br", "name": "Portuguese (Brazil)", "native": "Português (Brasil)"},
    {"code": "fr", "name": "French", "native": "Français"},
    {"code": "de", "name": "German", "native": "Deutsch"},
    {"code": "it", "name": "Italian", "native": "Italiano"},
    {"code": "ru", "name": "Russian", "native": "Русский"},
    {"code": "id", "name": "Indonesian", "native": "Bahasa Indonesia"},
    {"code": "tr", "name": "Turkish", "native": "Türkçe"},
    {"code": "pl", "name": "Polish", "native": "Polski"},
]

# Asian scripts requiring vertical layout analysis and English SFX equivalents
ASIAN_LANG_CODES = {"ko", "ja", "zh"}


def get_source_display_names() -> list[str]:
    """
    Constructs user-friendly display labels for source language combo boxes.

    Returns:
        list[str]: Formatted names like 'Korean (한국어)' or 'English'.
    """
    return [
        f"{lang['name']} ({lang['native']})" if lang["name"] != lang["native"] else lang["name"]
        for lang in SUPPORTED_SOURCE_LANGUAGES
    ]


def get_target_display_names() -> list[str]:
    """
    Constructs user-friendly display labels for target language combo boxes.

    Returns:
        list[str]: Formatted names like 'Spanish (Neutral) (Español Neutro)'.
    """
    return [
        f"{lang['name']} ({lang['native']})" if lang["name"] != lang["native"] else lang["name"]
        for lang in SUPPORTED_TARGET_LANGUAGES
    ]


def is_asian_source(source_text_or_code: str) -> bool:
    """
    Determines whether a given language identifier belongs to Asian scripts (CJK).

    Evaluates both ISO language codes ('ko', 'ja', 'zh') and UI display labels.

    Args:
        source_text_or_code (str): Language code or combo display text.

    Returns:
        bool: True if source language belongs to CJK group, False otherwise.
    """
    if not source_text_or_code:
        return False

    normalized = str(source_text_or_code).strip().lower()

    # Direct ISO code match
    if normalized in ASIAN_LANG_CODES:
        return True

    # Display string substring match
    return any(
        lang["name"].lower() in normalized or lang["native"].lower() in normalized
        for lang in SUPPORTED_SOURCE_LANGUAGES
        if lang["code"] in ASIAN_LANG_CODES
    )


def get_sfx_rule_for_target(target_display_text: str, is_asian_src: bool) -> str:
    """
    Generates localized comic onomatopoeia (SFX) translation instructions.

    Enforces target-specific conventions (e.g. inverted exclamation marks for Spanish,
    uppercase style for comics, or dual English SFX references for Asian sources).

    Args:
        target_display_text (str): Selected target language name or label.
        is_asian_src (bool): Whether the source comic originates from an Asian script.

    Returns:
        str: Formatted system prompt rule block.
    """
    if not target_display_text:
        target_clean = "target language"
    else:
        target_clean = target_display_text.split("(")[0].strip()

    target_lower = target_clean.lower()

    rule_lines = [
        "SFX RULE",
        f'Keep the exact text in "original". In "direct", write the {target_clean} comic onomatopoeia '
        "in UPPERCASE; never leave it untranslated unless that term is conventionally standard in the target language."
    ]

    # Target-specific localization examples
    if "spanish" in target_lower:
        rule_lines.append("Examples: ¡FUSH!, ¡PAM!, ¡CRASH!, ¡TOC-TOC!.")
    elif "portuguese" in target_lower:
        rule_lines.append("Examples: POW!, CRASH!, FWOOSH!, TOC-TOC!.")
    elif "english" in target_lower:
        rule_lines.append("Examples: BAM!, CRASH!, FWOOSH!, THUD!.")
    elif "french" in target_lower:
        rule_lines.append("Examples: BOUM!, CRAC!, VROUM!, TOC-TOC!.")

    rule_lines.append(
        "If it describes a visual action or emotional state rather than an audible sound, "
        "translate it as a concise action descriptor instead."
    )

    if is_asian_src:
        rule_lines.append(
            'In "sfx_en", provide the standard English comic sound equivalent (e.g., THUD, FWOOSH, GLARE).'
        )

    return " ".join(rule_lines)