import os
import re
import json
import base64
from io import BytesIO
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from PIL import Image

VALID_TYPES = {"bubble", "narration", "sfx", "outside"}
IGNORE_PATTERNS = re.compile(
    r"kakao\s*webtoon|tapas|webtoon\s*studio|scanlation|discord|https?://|www\.",
    re.IGNORECASE
)

class ProviderStatus(Enum):
    SUCCESS = auto()         # Dialogues extracted and translated
    EMPTY = auto()           # 200 OK but page is silent (no text)
    SAFETY_BLOCKED = auto()  # Content moderation filter triggered
    SERVER_BUSY = auto()     # 503 / 429 temporary overload
    QUOTA_EXHAUSTED = auto() # Daily quota exhausted (RPD)
    ERROR = auto()           # Fatal error / Bad Request

@dataclass
class TranslationResult:
    status: ProviderStatus
    bubbles: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0})
    message: str = ""
    raw_error: str = ""


class DailyQuotaExceeded(Exception):
    """Raised when an API provider completely exhausts its daily request limit (RPD)."""
    pass


class BaseAIProvider(ABC):
    """Abstract base class for all AI vision translation providers."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def test_and_fetch_models(self, key_or_url: str, auth_token: str = "") -> tuple[bool, list[str], str]:
        """Validates connection and returns available vision-compatible models."""
        pass

    @abstractmethod
    def execute_translation(
        self,
        image_path: str,
        prompt: str,
        model: str,
        api_key: str = "",
        endpoint_url: str = "",
        token: str = ""
    ) -> TranslationResult:
        """Sends multimodal payload and returns standardized TranslationResult."""
        pass

    @staticmethod
    def encode_image(image_path: str, target_w: int = 1100, quality: int = 85) -> str:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            w, h = img.size
            if w > target_w:
                ratio = target_w / float(w)
                target_h = int(h * ratio)
                img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            buffered = BytesIO()
            img.save(buffered, format="JPEG", quality=quality)
            return base64.b64encode(buffered.getvalue()).decode("utf-8")

    @staticmethod
    def clean_json_response(raw_text: str) -> dict:
        text = raw_text.strip()
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                text = text[start:end + 1]
        data = json.loads(text)
        if isinstance(data, list):
            data = {"bubbles": data}
        return data

    @staticmethod
    def normalize_bubbles(data: dict) -> list[dict]:
        raw_bubbles = data.get("bubbles", [])
        if not isinstance(raw_bubbles, list):
            return []

        cleaned = []
        for b in raw_bubbles:
            if not isinstance(b, dict):
                continue
            original = str(b.get("original", "")).strip()

            if not re.search(r"\w", original) or IGNORE_PATTERNS.search(original):
                continue

            b_type = str(b.get("type", "bubble")).lower()
            b["type"] = b_type if b_type in VALID_TYPES else "bubble"
            b["original"] = original

            for k in ("direct", "formal", "aggressive", "natural"):
                if k in b and b[k]:
                    b[k] = " ".join(str(b[k]).split())

            cleaned.append(b)

        for idx, b in enumerate(cleaned, start=1):
            b["id"] = idx

        return cleaned