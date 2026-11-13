import os
import json
import copy
from src.utils.paths import Paths
from src.utils.logger import logger
from src.backend.languages import is_asian_source, get_sfx_rule_for_target

# Reading order directives mapped by comic publication format
READING_ORDER = {
    "Manhwa": "Vertical webtoon scroll: top-to-bottom, left-to-right within the same row.",
    "Manga": "Japanese format: right-to-left, top-to-bottom.",
    "Comic": "Western format: left-to-right, top-to-bottom.",
    "Manhua": "Vertical scroll: top-to-bottom, left-to-right within the same row.",
}

# NOTE FOR MAINTAINERS:
# DO NOT alter the core rules text below. Changing rule numbering or phrasing (especially Rule 7)
# directly impacts how multimodal vision models handle silent panels and empty pages.
DEFAULT_CORE_RULES = r"""# CORE EXTRACTION ENGINE
Extract every text entity on the attached page, following the reading order given in ACTIVE MEDIUM:
speech bubbles, narration boxes/captions, sound effects (SFX) and floating outside text.

RULES
1. One element per visual unit. Never merge separate bubbles or panels. Never skip short or incomplete fragments (a single word, or a sentence cut off at a page edge such as "HOW LONG HAS IT"), including text at the very top or bottom.
2. Transcribe the exact text into "original" so the editor can verify it. Translate strictly from the source language to the target language.
3. Sentences often continue across bubbles and pages. If a PREVIOUS PAGE CONTEXT block is present, use it only for continuity; it is not part of this page, never return it.
4. IGNORE and do not return: watermarks, scanlator or studio credits, logos, URLs, page numbers and isolated symbols (#, *, ♪).
5. Variants (formal, aggressive, natural): fill one only if it differs meaningfully from "direct"; otherwise use "". Never fill them for SFX.
6. "subtext": one short sentence only when the tone is not obvious; otherwise "". Never name a character in subtext unless an explicit name label is visible on the page.
7. If the page has no translatable text, return {"bubbles": []}.
8. Follow the USER RULES below for tone, pronouns, glossary and lore.
9. Write every translation as a single clean line. Never insert line breaks (\n), even if the original text is split across several lines inside the bubble.
10. Continuity punctuation: if a sentence is split across bubbles or page boundaries, follow the target language's punctuation and capitalization conventions. Do not add a terminal period to a clearly incomplete fragment; make the continuing fragment read naturally with it.
"""

DEFAULT_USER_RULES = ""
DEFAULT_EXTRACTION_OPTIONS = {
    "sfx": True,
    "sfx_meaning": False,
    "narration": True,
    "outside": True,
    "variants": True,
    "subtext": True,
    "r19_mode": False,
}


class PromptManager:
    """
    Manages system rules, custom lore/glossary guidelines, and prompt assembly
    for multimodal vision LLMs (Gemini, Ollama, and external endpoints).
    """

    def __init__(self):
        self.user_rules_file = os.path.join(Paths.CACHE, "user_rules.txt")
        self.core_rules_file = os.path.join(Paths.CACHE, "core_rules.txt")
        self.options_file = os.path.join(Paths.CACHE, "prompt_options.json")

        self.user_rules = self._load_file(self.user_rules_file, DEFAULT_USER_RULES)
        self.core_rules = self._load_file(self.core_rules_file, DEFAULT_CORE_RULES)
        self.options = self._load_options()

        # Automatic schema invalidation:
        # Detects outdated cached versions of core_rules.txt from previous studio releases
        # and safely overwrites them with the current engine specification.
        if (
            '"original":' in self.core_rules
            or "Never skip short or incomplete fragments" not in self.core_rules
            or "must open with ¿ or ¡" in self.core_rules
        ):
            self.core_rules = DEFAULT_CORE_RULES
            self.save_core_rules(self.core_rules)

    def _load_file(self, file_path: str, fallback: str) -> str:
        """
        Safely reads a text file from disk, falling back to a default value if missing.
        """
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as e:
                logger.error(f"[PROMPT_MANAGER] Could not read {file_path}: {e}")
        return fallback

    def save_user_rules(self, text: str):
        """
        Persists custom user guidelines, character lore, and glossary terms to disk.
        """
        self.user_rules = text.strip()
        try:
            os.makedirs(Paths.CACHE, exist_ok=True)
            with open(self.user_rules_file, "w", encoding="utf-8") as f:
                f.write(self.user_rules)
        except Exception as e:
            logger.error(f"[PROMPT_MANAGER] Error saving user rules: {e}")

    def save_core_rules(self, text: str):
        """
        Persists engine technical constraints to disk.
        """
        self.core_rules = text.strip()
        try:
            os.makedirs(Paths.CACHE, exist_ok=True)
            with open(self.core_rules_file, "w", encoding="utf-8") as f:
                f.write(self.core_rules)
        except Exception as e:
            logger.error(f"[PROMPT_MANAGER] Error saving core rules: {e}")

    def _load_options(self) -> dict:
        """Loads optional prompt features while supplying defaults for older installs."""
        options = copy.deepcopy(DEFAULT_EXTRACTION_OPTIONS)
        if not os.path.exists(self.options_file):
            return options
        try:
            with open(self.options_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                for name in options:
                    if name in loaded:
                        options[name] = bool(loaded[name])
        except Exception as e:
            logger.error(f"[PROMPT_MANAGER] Could not read {self.options_file}: {e}")
        return options

    def save_options(self, options: dict):
        """Persists prompt feature toggles in the cache directory."""
        self.options = copy.deepcopy(DEFAULT_EXTRACTION_OPTIONS)
        for name in self.options:
            if name in options:
                self.options[name] = bool(options[name])
        try:
            os.makedirs(Paths.CACHE, exist_ok=True)
            with open(self.options_file, "w", encoding="utf-8") as f:
                json.dump(self.options, f, indent=2)
        except Exception as e:
            logger.error(f"[PROMPT_MANAGER] Error saving prompt options: {e}")

    def _build_options_block(self, enabled_types: list[str], options: dict) -> str:
        """Builds explicit instructions that take precedence over the technical rules."""
        lines = [
            "[ACTIVE EXTRACTION OPTIONS — these choices override conflicting instructions above]",
            f"- Extract these entity types only: {', '.join(enabled_types)}.",
        ]
        if not options["sfx"]:
            lines.append("- Ignore all sound effects and comic onomatopoeias; do not return them.")
        if not options["narration"]:
            lines.append("- Ignore narration boxes and captions; do not return them.")
        if not options["outside"]:
            lines.append("- Ignore floating text outside speech bubbles and narration boxes; do not return it.")
        if not options["variants"]:
            lines.append("- Return only the direct translation. Do not generate formal, aggressive, or natural variants.")
        if not options["subtext"]:
            lines.append("- Do not generate subtext or tone notes.")
        if options.get("r19_mode", False):
            lines.extend([
                "",
                "[R19 MODE — CONTEXTUAL VOCALIZATION LOCALIZATION]",
                "- Use the full artwork and surrounding narrative context to distinguish laughter from breathing, sighs, effort, pain, surprise, or other vocalizations.",
                "- In clearly intimate scenes, do not turn a breathy vocalization into laughter only because its source spelling contains H or HA.",
                "- Preserve the exact visible lettering in original. In direct, render the vocalization naturally according to the selected target language's conventions, preserving its length and punctuation where practical.",
                "- Apply this only to spoken vocalizations; continue to classify and translate sound-effect lettering according to the SFX rules. If context is ambiguous, do not invent laughter.",
            ])
        if options["sfx"] and options.get("sfx_meaning", False):
            lines.extend([
                "",
                "[SFX MEANING OPTION]",
                '- For each entity with type "sfx", include an "sfx_meaning" field with a concise explanation of what the sound conveys in context.',
                "- Write the explanation in the selected target language. It is a semantic gloss, not another onomatopoeia or a replacement for direct.",
                '- If the meaning is unclear, use an empty string. Do not add "sfx_meaning" to entities of other types.',
            ])
        return "\n".join(lines)

    def build_full_prompt(
        self,
        src_lang: str,
        tgt_lang: str,
        medium: str,
        *,
        user_rules: str = None,
        options: dict = None,
    ) -> str:
        """
        Assembles the comprehensive system prompt for inference.

        Combines:
        1. Fixed extraction constraints (core rules).
        2. Target-specific SFX handling and localization rules.
        3. Active medium reading order (Manhwa, Manga, Comic, Manhua).
        4. Language pair specification.
        5. Strict JSON output schema.
        6. Custom user style rules (if defined).

        Returns:
            str: Full assembled instruction prompt.
        """
        asian_src = is_asian_source(src_lang)
        
        # Case-insensitive reading order lookup with Manhwa fallback
        norm_medium = medium.strip().title() if medium else "Manhwa"
        medium_order = READING_ORDER.get(norm_medium, READING_ORDER["Manhwa"])

        medium_block = (
            f"[ACTIVE MEDIUM: {norm_medium.upper()}]\n"
            f"- Reading order: {medium_order}"
        )
        lang_block = (
            "[LANGUAGE]\n"
            f"- Source language: {src_lang}\n"
            f"- Target language: {tgt_lang} (fluid, natural, high-quality scanlation)"
        )

        active_options = copy.deepcopy(DEFAULT_EXTRACTION_OPTIONS)
        active_options.update(options if options is not None else self.options)
        enabled_types = ["bubble"]
        if active_options["narration"]:
            enabled_types.append("narration")
        if active_options["sfx"]:
            enabled_types.append("sfx")
        if active_options["outside"]:
            enabled_types.append("outside")

        sfx_rule = (
            get_sfx_rule_for_target(tgt_lang, asian_src)
            if active_options["sfx"] else ""
        )
        sfx_meaning_enabled = active_options["sfx"] and active_options.get("sfx_meaning", False)

        schema_fields = [
            ('"id"', "1"),
            ('"type"', '"bubble"'),
            ('"original"', '"exact text on the page"'),
            ('"direct"', '"primary translation"'),
        ]
        if active_options["variants"]:
            schema_fields.extend([
                ('"formal"', '"variant or empty string"'),
                ('"aggressive"', '"variant or empty string"'),
                ('"natural"', '"variant or empty string"'),
            ])
        if active_options["subtext"]:
            schema_fields.append(('"subtext"', '"short note or empty string"'))
        if active_options["sfx"] and asian_src:
            schema_fields.append(('"sfx_en"', '"English equivalent for SFX, otherwise empty string"'))

        field_lines = [f"    {key}: {value}" for key, value in schema_fields]
        field_lines = [line + ("," if i < len(field_lines) - 1 else "") for i, line in enumerate(field_lines)]
        schema_block = (
            "OUTPUT: valid JSON only, no markdown, no comments, exactly this shape:\n"
            '{"bubbles": [\n  {\n'
            + "\n".join(field_lines)
            + "\n  }\n]}\n"
            + f'"type" must be one of: {", ".join(enabled_types)}.'
        )
        if sfx_meaning_enabled:
            schema_block += (
                '\nWhen this option is active, entities with type "sfx" must also include '
                '"sfx_meaning"; omit this field from all other entity types.'
            )

        parts = [self.core_rules]
        if sfx_rule:
            parts.append(sfx_rule)
        parts.extend([medium_block, lang_block, schema_block])
        active_user_rules = self.user_rules if user_rules is None else user_rules
        if active_user_rules.strip():
            parts.append(f"# USER RULES\n{active_user_rules.strip()}")
        parts.append(self._build_options_block(enabled_types, active_options))

        return "\n\n".join(parts)

    def build_continuity_context(
        self, 
        current_path: str, 
        all_project_paths: list[str], 
        page_bubbles_data: dict, 
        page_language_pairs: dict = None,
        language_pair: tuple[str, str] = None,
        max_pairs: int = 3
    ) -> str:
        """
        Extracts dialogue from the immediately preceding page to provide narrative continuity.

        Prevents broken clauses across page transitions by supplying the model with the
        final translated lines of the previous image without confusing them with active dialogues.

        Args:
            current_path (str): File path of the page being processed.
            all_project_paths (list[str]): Ordered list of all image paths in the current project.
            page_bubbles_data (dict): Cache of extracted bubble dictionaries mapped by path.
            page_language_pairs (dict): Source/target language pair used to generate each page's translation.
            language_pair (tuple): Active source/target pair; mismatched previous pages are ignored.
            max_pairs (int): Maximum number of dialogue pairs to inject as continuity context.

        Returns:
            str: Continuity context block, or empty string if not applicable.
        """
        if not current_path or not all_project_paths:
            return ""

        # Normalize file paths to avoid cross-platform slash mismatch
        norm_current = os.path.normpath(current_path)
        norm_all_paths = [os.path.normpath(p) for p in all_project_paths]

        if norm_current not in norm_all_paths:
            return ""

        idx = norm_all_paths.index(norm_current)
        if idx == 0:
            return ""

        prev_path = all_project_paths[idx - 1]

        # Never feed a translation from another language pair into the current request.
        if page_language_pairs is not None:
            previous_pair = page_language_pairs.get(prev_path)
            if previous_pair is None:
                previous_pair = page_language_pairs.get(os.path.normpath(prev_path))
            if not language_pair or previous_pair != language_pair:
                return ""
        
        # Retrieve parsed bubble entries using both original and normalized keys
        bubbles = page_bubbles_data.get(prev_path) or page_bubbles_data.get(os.path.normpath(prev_path)) or []

        pairs = []
        for b in bubbles:
            if b.get("type") == "sfx":
                continue
            orig = str(b.get("original", "")).replace("\n", " ").strip()
            tr = (b.get("final") or b.get("direct") or "").replace("\n", " ").strip()
            if orig and tr:
                pairs.append((orig, tr))

        pairs = pairs[-max_pairs:]
        if not pairs:
            return ""

        lines = "\n".join(f'- "{o}" -> "{t}"' for o, t in pairs)
        return (
            "\n\n# PREVIOUS PAGE CONTEXT (continuity only; do NOT return these lines)\n"
            f"{lines}\n"
            "If the first bubble(s) of this page continue one of these fragments, translate them "
            "so both parts read as one natural sentence, adapting to the translation above.\n"
        )
