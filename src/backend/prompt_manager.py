import os
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
10. Continuity punctuation: if a sentence is split across bubbles or page boundaries, the opening fragment must open with ¿ or ¡ (if applicable) and not end with a period; the continuing fragment must begin in lowercase and close with ? or !.
"""

DEFAULT_USER_RULES = ""


class PromptManager:
    """
    Manages system rules, custom lore/glossary guidelines, and prompt assembly
    for multimodal vision LLMs (Gemini, Ollama, and external endpoints).
    """

    def __init__(self):
        self.user_rules_file = os.path.join(Paths.CACHE, "user_rules.txt")
        self.core_rules_file = os.path.join(Paths.CACHE, "core_rules.txt")

        self.user_rules = self._load_file(self.user_rules_file, DEFAULT_USER_RULES)
        self.core_rules = self._load_file(self.core_rules_file, DEFAULT_CORE_RULES)

        # Automatic schema invalidation:
        # Detects outdated cached versions of core_rules.txt from previous studio releases
        # and safely overwrites them with the current engine specification.
        if '"original":' in self.core_rules or "Never skip short or incomplete fragments" not in self.core_rules:
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

    def build_full_prompt(self, src_lang: str, tgt_lang: str, medium: str) -> str:
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

        sfx_rule = get_sfx_rule_for_target(tgt_lang, asian_src)
        sfx_en_line = (',\n    "sfx_en": "English equivalent for SFX, otherwise empty string"'
                       if asian_src else "")

        schema_block = (
            "OUTPUT: valid JSON only, no markdown, no comments, exactly this shape:\n"
            '{"bubbles": [\n  {\n'
            '    "id": 1,\n'
            '    "type": "bubble",\n'
            '    "original": "exact text on the page",\n'
            '    "direct": "primary translation",\n'
            '    "formal": "variant or empty string",\n'
            '    "aggressive": "variant or empty string",\n'
            '    "natural": "variant or empty string",\n'
            '    "subtext": "short note or empty string"' + sfx_en_line + "\n"
            "  }\n]}\n"
            '"type" must be one of: bubble, narration, sfx, outside.'
        )

        parts = [self.core_rules, sfx_rule, medium_block, lang_block, schema_block]
        if self.user_rules.strip():
            parts.append(f"# USER RULES\n{self.user_rules.strip()}")

        return "\n\n".join(parts)

    def build_continuity_context(
        self, 
        current_path: str, 
        all_project_paths: list[str], 
        page_bubbles_data: dict, 
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