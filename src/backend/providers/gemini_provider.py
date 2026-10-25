import time
import requests
from src.backend.providers.base_provider import (
    BaseAIProvider, 
    TranslationResult, 
    ProviderStatus, 
    DailyQuotaExceeded
)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# The 4 official harm categories configurable in Google Gemini API
SAFETY_SETTINGS_BLOCK_NONE = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# Official BlockedReason enums (Input / Prompt Feedback)
PROMPT_BLOCK_REASONS = {
    "SAFETY": "Image flagged by Gemini safety threshold.",
    "PROHIBITED_CONTENT": "Image flagged for prohibited content policy.",
    "BLOCKLIST": "Terms matched a restricted blocklist.",
    "MODEL_ARMOR": "Blocked by Google Model Armor security layer.",
    "JAILBREAK": "Blocked by jailbreak detection heuristic.",
    "BLOCKED_REASON_UNSPECIFIED": "Blocked by Google for an unspecified reason.",
    "OTHER": "Blocked due to unsupported language or region constraint.",
}

# Official FinishReason enums (Output / Response Candidates)
UNSAFE_FINISH_REASONS = {
    "SAFETY": "Output text triggered Gemini safety filter.",
    "PROHIBITED_CONTENT": "Output text contained prohibited content.",
    "SPII": "Output blocked due to Sensitive Personally Identifiable Information.",
    "RECITATION": "Output blocked due to source text recitation restriction.",
}


class GeminiProvider(BaseAIProvider):
    def __init__(self):
        super().__init__("gemini")

    def test_and_fetch_models(self, key_or_url: str, auth_token: str = "") -> tuple[bool, list[str], str]:
        key = key_or_url.strip()
        if not key:
            return False, [], "Please provide a valid Gemini API Key."

        url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
        headers = {"x-goog-api-key": key}

        try:
            res = requests.get(url, headers=headers, timeout=12)
            if res.status_code in (400, 403):
                return False, [], "Invalid API Key or unauthorized access by Google."
            res.raise_for_status()

            raw_models = res.json().get("models", [])
            supported = []
            for m in raw_models:
                name = m.get("name", "").replace("models/", "")
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods and ("flash" in name or "pro" in name):
                    supported.append(name)

            supported.sort(key=lambda x: (not ("flash" in x), x))
            return True, supported or ["gemini-3.1-flash-lite", "gemini-1.5-flash"], "Connected successfully to Google Gemini."
        except Exception as e:
            return False, [], f"Connection error: {str(e)}"

    def execute_translation(
        self,
        image_path: str,
        prompt: str,
        model: str,
        api_key: str = "",
        endpoint_url: str = "",
        token: str = ""
    ) -> TranslationResult:
        b64_img = self.encode_image(image_path)
        usage_info = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        max_retries = 2

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {
            "x-goog-api-key": api_key.strip(),
            "Content-Type": "application/json"
        }
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}}
                ]
            }],
            "safetySettings": SAFETY_SETTINGS_BLOCK_NONE,
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.2,
                "maxOutputTokens": 4096
            }
        }

        for attempt in range(max_retries + 1):
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=90)

                # Daily request limit exceeded (RPD)
                if res.status_code == 429:
                    body_err = res.text
                    if any(term in body_err for term in ("PerDay", "ResourceExhausted", "RESOURCE_EXHAUSTED")):
                        raise DailyQuotaExceeded("Daily request limit exhausted for Gemini (RPD).")
                    if attempt < max_retries:
                        time.sleep(8 * (attempt + 1))
                        continue
                    return TranslationResult(
                        status=ProviderStatus.SERVER_BUSY,
                        usage=usage_info,
                        message="Rate limit reached (429). Retry in a few minutes.",
                        raw_error=res.text[:120]
                    )

                # Transient server errors (503 / 500 / 502 / 504)
                if res.status_code in RETRYABLE_STATUS_CODES:
                    if attempt < max_retries:
                        time.sleep(5 * (attempt + 1))
                        continue
                    return TranslationResult(
                        status=ProviderStatus.SERVER_BUSY,
                        usage=usage_info,
                        message=f"Google servers unavailable ({res.status_code}). Temporary overload, retry later.",
                        raw_error=res.text[:120]
                    )

                # Client-side non-retryable errors
                if res.status_code in (400, 401, 403, 404):
                    return TranslationResult(
                        status=ProviderStatus.ERROR,
                        usage=usage_info,
                        message=f"Client error ({res.status_code}): Check API key or payload parameters.",
                        raw_error=res.text[:200]
                    )

                res.raise_for_status()
                res_json = res.json()

                # Parse token consumption metadata
                meta = res_json.get("usageMetadata", {})
                p_tok = meta.get("promptTokenCount", 0)
                c_tok = meta.get("candidatesTokenCount", 0)
                usage_info = {"prompt_tokens": p_tok, "output_tokens": c_tok, "total_tokens": p_tok + c_tok}

                # 1. EVALUATION OF INPUT PROMPT FEEDBACK (BlockedReason Enum)
                prompt_feedback = res_json.get("promptFeedback", {})
                block_reason = prompt_feedback.get("blockReason")
                if block_reason:
                    reason_desc = PROMPT_BLOCK_REASONS.get(block_reason, f"Blocked: {block_reason}")
                    return TranslationResult(
                        status=ProviderStatus.SAFETY_BLOCKED,
                        usage=usage_info,
                        message=f"Gemini input rejected: {reason_desc} Switch LLM provider.",
                        raw_error=f"promptFeedback.blockReason={block_reason}"
                    )

                # 2. CANDIDATES EXISTENCE VALIDATION
                candidates = res_json.get("candidates", [])
                if not candidates:
                    return TranslationResult(
                        status=ProviderStatus.SAFETY_BLOCKED,
                        usage=usage_info,
                        message="Gemini returned 0 candidates (image filtered pre-generation). Switch LLM provider.",
                        raw_error="candidates=[]"
                    )

                cand = candidates[0]
                finish_reason = cand.get("finishReason", "")

                # 3. EVALUATION OF OUTPUT FINISH REASON (FinishReason Enum)
                if finish_reason in UNSAFE_FINISH_REASONS:
                    reason_desc = UNSAFE_FINISH_REASONS[finish_reason]
                    return TranslationResult(
                        status=ProviderStatus.SAFETY_BLOCKED,
                        usage=usage_info,
                        message=f"Generation halted: {reason_desc} Switch LLM provider.",
                        raw_error=f"finishReason={finish_reason}"
                    )

                if finish_reason and finish_reason not in ("STOP", ""):
                    return TranslationResult(
                        status=ProviderStatus.ERROR,
                        usage=usage_info,
                        message=f"Unexpected finishReason: {finish_reason}",
                        raw_error=f"finishReason={finish_reason}"
                    )

                # Extract content parts, discarding thought blocks
                parts = cand.get("content", {}).get("parts", [])
                text_parts = [p.get("text", "") for p in parts if "text" in p and not p.get("thought", False)]
                raw_text = "".join(text_parts).strip()

                parsed_dict = self.clean_json_response(raw_text)
                bubbles = self.normalize_bubbles(parsed_dict)

                if not bubbles:
                    return TranslationResult(
                        status=ProviderStatus.EMPTY,
                        bubbles=[],
                        usage=usage_info,
                        message="No text detected on this page (silent panel)."
                    )

                return TranslationResult(
                    status=ProviderStatus.SUCCESS,
                    bubbles=bubbles,
                    usage=usage_info,
                    message=f"Successfully extracted {len(bubbles)} dialogue(s)."
                )

            except DailyQuotaExceeded:
                raise
            except requests.exceptions.Timeout:
                # Handle socket or read timeouts when remote infrastructure is congested
                if attempt < max_retries:
                    time.sleep(4 * (attempt + 1))
                    continue
                return TranslationResult(
                    status=ProviderStatus.SERVER_BUSY,
                    usage=usage_info,
                    message="Google server timed out (>90s). Infrastructure congested, retry later.",
                    raw_error="Read timed out (90s)"
                )
            except Exception as e:
                if attempt == max_retries:
                    return TranslationResult(
                        status=ProviderStatus.ERROR,
                        usage=usage_info,
                        message=f"Extraction failed: {str(e)}",
                        raw_error=str(e)
                    )
                time.sleep(3)

        return TranslationResult(status=ProviderStatus.ERROR, message="Unexpected loop termination.")