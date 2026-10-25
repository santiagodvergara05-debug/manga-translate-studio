"""Language definitions and onomatopoeia adaptation rules."""

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

ASIAN_LANG_CODES = {"ko", "ja", "zh"}


def get_source_display_names() -> list[str]:
    return [f"{lang['name']} ({lang['native']})" if lang['name'] != lang['native'] else lang['name'] 
            for lang in SUPPORTED_SOURCE_LANGUAGES]


def get_target_display_names() -> list[str]:
    return [f"{lang['name']} ({lang['native']})" if lang['name'] != lang['native'] else lang['name'] 
            for lang in SUPPORTED_TARGET_LANGUAGES]


def is_asian_source(source_display_text: str) -> bool:
    text_lower = source_display_text.lower()
    return any(lang["name"].lower() in text_lower or lang["native"].lower() in text_lower 
               for lang in SUPPORTED_SOURCE_LANGUAGES if lang["code"] in ASIAN_LANG_CODES)


def get_sfx_rule_for_target(target_display_text: str, is_asian_src: bool) -> str:
    target_clean = target_display_text.split("(")[0].strip()
    
    rule = (
        "SFX RULE\n"
        f'Keep the exact text in "original". In "direct" write the {target_clean} comic onomatopoeia '
        "in uppercase; never leave it untouched unless that is how it is conventionally used in the target language."
    )
    
    if "Spanish" in target_clean:
        rule += " Examples: ¡FUSH!, ¡PAM!, ¡CRASH!."
    elif "English" in target_clean:
        rule += " Examples: BAM!, CRASH!, FWOOSH!."

    rule += " If it describes a visual action rather than an audible sound, use a concise action term instead."
    
    if is_asian_src:
        rule += ' In "sfx_en" provide the standard English comic sound equivalent (e.g. THUD, FWOOSH).'
        
    return rule