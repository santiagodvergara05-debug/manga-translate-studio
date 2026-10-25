import os
import re
import sys
import json
import time
import base64
import requests
from io import BytesIO
from PIL import Image

from PySide6.QtCore import Signal, QThread
from src.utils.logger import logger

# Desactivado automáticamente si corre compilado con PyInstaller (.exe)
DEBUG_AI_LOGS = (not getattr(sys, "frozen", False)) and os.environ.get("MTS_DEBUG", "1") == "1"

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
VALID_TYPES = {"bubble", "narration", "sfx", "outside"}
IGNORE_PATTERNS = re.compile(
    r"kakao\s*webtoon|tapas|webtoon\s*studio|scanlation|discord|https?://|www\.",
    re.IGNORECASE
)


class DailyQuotaExceeded(Exception):
    """Excepción específica cuando Gemini o el proveedor agota la cuota diaria (RPD)."""
    pass


def _print_debug_banner(title: str):
    print("\n" + "=" * 75)
    print(f" [AI DEBUG] - {title}")
    print("=" * 75)


def _debug_log_response(provider: str, usage_info: dict, raw_text: str, bubbles: list):
    if not DEBUG_AI_LOGS:
        return
    _print_debug_banner(f"RESPUESTA RECIBIDA DE {provider.upper()}")
    print(f"[*] Tokens Entrada: {usage_info.get('prompt_tokens', 0):,}")
    print(f"[*] Tokens Salida: {usage_info.get('output_tokens', 0):,}")
    print(f"[*] Total Tokens Facturados: {usage_info.get('total_tokens', 0):,}")
    print("\n--- [JSON BRUTO DEL MODELO] ---")
    print(raw_text.strip())
    print("-" * 75)
    print(f"[*] Entidades/Globos detectados válidos: {len(bubbles)}")
    for b in bubbles:
        orig = b.get("original", "").replace("\n", " ")
        direct = b.get("direct", "").replace("\n", " ")
        print(f"  • [#{b.get('id', '?')}] {b.get('type', 'bubble').upper()}: '{orig}' -> '{direct}'")
    print("=" * 75 + "\n")


class AIClientManager:
    @staticmethod
    def normalize_url(url: str, default: str = "https://ollama.com/v1") -> str:
        clean = url.strip() if url else default
        if not clean:
            clean = default
        if not clean.startswith("http://") and not clean.startswith("https://"):
            if any(local in clean.lower() for local in ("localhost", "127.0.0.1", "192.168.", "10.", "172.")):
                clean = f"http://{clean}"
            else:
                clean = f"https://{clean}"
        return clean.rstrip("/")

    @staticmethod
    def estimate_tokens(prompt: str, image_path: str = None) -> tuple[int, int, int]:
        text_tokens = max(1, int(len(prompt) / 3.6))
        image_tokens = 0

        if image_path and os.path.exists(image_path):
            try:
                with Image.open(image_path) as img:
                    w, h = img.size
                    tiles_w = max(1, (w + 511) // 512)
                    tiles_h = max(1, (h + 511) // 512)
                    total_tiles = min(tiles_w * tiles_h, 4)
                    image_tokens = 258 + (total_tiles * 280)
            except Exception:
                image_tokens = 1120
        else:
            image_tokens = 1120

        total = text_tokens + image_tokens
        return total, text_tokens, image_tokens

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
            direct = str(b.get("direct", "")).strip()

            if not re.search(r"\w", original) or IGNORE_PATTERNS.search(original):
                continue

            b_type = str(b.get("type", "bubble")).lower()
            b["type"] = b_type if b_type in VALID_TYPES else "bubble"
            b["original"] = original
            
            # Aplana saltos de línea para evitar dobles barras accidentales (//) en el TXT
            for k in ("direct", "formal", "aggressive", "natural"):
                if k in b and b[k]:
                    b[k] = " ".join(str(b[k]).split())

            cleaned.append(b)

        for idx, b in enumerate(cleaned, start=1):
            b["id"] = idx

        return cleaned

    @staticmethod
    def test_and_fetch_models(provider: str, key_or_url: str, auth_token: str = "") -> tuple[bool, list[str], str]:
        provider = provider.lower()

        try:
            if provider == "gemini":
                key = key_or_url.strip()
                if not key:
                    return False, [], "Ingresa una Gemini API Key válida."

                url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
                headers = {"x-goog-api-key": key}
                res = requests.get(url, headers=headers, timeout=12)

                if res.status_code in (400, 403):
                    return False, [], "API Key inválida o no autorizada por Google."
                res.raise_for_status()

                raw_models = res.json().get("models", [])
                supported = []
                for m in raw_models:
                    name = m.get("name", "").replace("models/", "")
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" in methods and ("flash" in name or "pro" in name):
                        supported.append(name)

                supported.sort(key=lambda x: (not ("flash" in x), x))
                return True, supported or ["gemini-3.1-flash-lite", "gemini-1.5-flash"], "Conectado exitosamente a Gemini."

            elif provider == "ollama":
                base_url = AIClientManager.normalize_url(key_or_url)
                token = auth_token.strip()
                headers = {"Authorization": f"Bearer {token}"} if token else {}

                if base_url.endswith("/v1"):
                    res = requests.get(f"{base_url}/models", headers=headers, timeout=10)
                    if res.status_code == 200:
                        models = [m.get("id") for m in res.json().get("data", []) if m.get("id")]
                        if models:
                            return True, models, "Conectado a Ollama Cloud (/v1)."
                    elif res.status_code in (401, 403):
                        return False, [], "Token/API Key de Ollama inválido o ausente."

                try:
                    res_local = requests.get(f"{base_url}/api/tags", headers=headers, timeout=8)
                    if res_local.status_code == 200:
                        models = [m.get("name") for m in res_local.json().get("models", []) if m.get("name")]
                        if models:
                            return True, models, "Conectado a Ollama Local."
                except Exception:
                    pass

                res_fb = requests.get(f"{base_url}/models", headers=headers, timeout=8)
                if res_fb.status_code == 200:
                    models = [m.get("id") for m in res_fb.json().get("data", []) if m.get("id")]
                    if models:
                        return True, models, "Conectado a Ollama."

                return False, [], f"No se pudo consultar modelos en {base_url}."

            return False, [], "Proveedor desconocido."
        except Exception as e:
            return False, [], f"Error de conexión: {str(e)}"

    @staticmethod
    def execute_translation_request(image_path: str, prompt: str, provider: str, model: str, api_key: str, endpoint_url: str, token: str) -> tuple[list[dict], dict]:
        b64_img = AIClientManager.encode_image(image_path)
        provider = provider.lower()
        usage_info = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        if DEBUG_AI_LOGS:
            _print_debug_banner("PAYLOAD ENVIADO A LA API")
            print(f"[*] Archivo de imagen: {os.path.basename(image_path)}")
            print(f"[*] Proveedor: {provider.upper()}")
            print(f"[*] Modelo seleccionado: {model}")
            print(f"[*] Tamaño Base64: ~{len(b64_img):,} caracteres")
            print("\n--- [PROMPT / INSTRUCCIONES] ---")
            print(prompt.strip())
            print("-" * 75)

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                if provider == "gemini":
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
                        "generationConfig": {
                            "response_mime_type": "application/json",
                            "temperature": 0.2,
                            "maxOutputTokens": 4096
                        }
                    }
                    res = requests.post(url, headers=headers, json=payload, timeout=90)

                    if res.status_code == 429:
                        body_err = res.text
                        if any(term in body_err for term in ("PerDay", "ResourceExhausted", "RESOURCE_EXHAUSTED")):
                            raise DailyQuotaExceeded("DAILY_QUOTA: Cuota diaria de Gemini agotada (RPD).")
                        if attempt < max_retries:
                            time.sleep(10 * (attempt + 1))
                            continue

                    if res.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries:
                        time.sleep(4)
                        continue

                    res.raise_for_status()

                    res_json = res.json()
                    candidates = res_json.get("candidates", [])
                    if not candidates:
                        raise ValueError("Gemini no devolvió candidatos en la respuesta.")

                    cand = candidates[0]
                    finish_reason = cand.get("finishReason", "")
                    if finish_reason and finish_reason not in ("STOP", ""):
                        raise ValueError(f"Gemini interrumpió la traducción con finishReason={finish_reason}")

                    raw_text = cand["content"]["parts"][0]["text"]
                    parsed_dict = AIClientManager.clean_json_response(raw_text)
                    bubbles = AIClientManager.normalize_bubbles(parsed_dict)

                    meta = res_json.get("usageMetadata", {})
                    p_tok = meta.get("promptTokenCount", 0)
                    c_tok = meta.get("candidatesTokenCount", 0)
                    t_tok = meta.get("totalTokenCount", p_tok + c_tok)
                    usage_info = {"prompt_tokens": p_tok, "output_tokens": c_tok, "total_tokens": t_tok}

                    _debug_log_response("Gemini", usage_info, raw_text, bubbles)
                    return bubbles, usage_info

                elif provider == "ollama":
                    base_url = AIClientManager.normalize_url(endpoint_url)
                    headers = {"Content-Type": "application/json"}
                    if token.strip():
                        headers["Authorization"] = f"Bearer {token.strip()}"

                    if base_url.endswith("/v1"):
                        url = f"{base_url}/chat/completions"
                        payload = {
                            "model": model,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": prompt},
                                        {
                                            "type": "image_url",
                                            "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}
                                        }
                                    ]
                                }
                            ],
                            "temperature": 0.2,
                            "response_format": {"type": "json_object"}
                        }
                        res = requests.post(url, headers=headers, json=payload, timeout=120)

                        if res.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries:
                            time.sleep(4)
                            continue

                        res.raise_for_status()
                        res_json = res.json()
                        raw_text = res_json["choices"][0]["message"]["content"]
                        parsed_dict = AIClientManager.clean_json_response(raw_text)
                        bubbles = AIClientManager.normalize_bubbles(parsed_dict)

                        u = res_json.get("usage", {})
                        p_tok = u.get("prompt_tokens", 0)
                        c_tok = u.get("completion_tokens", 0)
                        t_tok = u.get("total_tokens", p_tok + c_tok)
                        usage_info = {"prompt_tokens": p_tok, "output_tokens": c_tok, "total_tokens": t_tok}

                    else:
                        url = f"{base_url}/api/generate"
                        payload = {
                            "model": model,
                            "prompt": prompt,
                            "images": [b64_img],
                            "stream": False,
                            "format": "json",
                            "options": {
                                "num_ctx": 8192,
                                "temperature": 0.2
                            }
                        }
                        res = requests.post(url, headers=headers, json=payload, timeout=120)

                        if res.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries:
                            time.sleep(4)
                            continue

                        res.raise_for_status()
                        res_json = res.json()
                        raw_text = res_json.get("response", "{}")
                        parsed_dict = AIClientManager.clean_json_response(raw_text)
                        bubbles = AIClientManager.normalize_bubbles(parsed_dict)

                        p_tok = res_json.get("prompt_eval_count", 0)
                        c_tok = res_json.get("eval_count", 0)
                        usage_info = {"prompt_tokens": p_tok, "output_tokens": c_tok, "total_tokens": p_tok + c_tok}

                    _debug_log_response("Ollama", usage_info, raw_text, bubbles)
                    return bubbles, usage_info

            except DailyQuotaExceeded:
                raise
            except Exception as e:
                status_code = getattr(getattr(e, "response", None), "status_code", None)
                if status_code and status_code not in RETRYABLE_STATUS_CODES:
                    raise e
                if attempt == max_retries:
                    raise e
                time.sleep(3)

        return [], usage_info


class FetchModelsWorker(QThread):
    finished = Signal(bool, list, str)

    def __init__(self, provider: str, key_or_url: str, auth_token: str = ""):
        super().__init__()
        self.provider = provider
        self.key_or_url = key_or_url
        self.auth_token = auth_token

    def run(self):
        success, models, msg = AIClientManager.test_and_fetch_models(
            self.provider, self.key_or_url, self.auth_token
        )
        self.finished.emit(success, models, msg)


class MultimodalTranslationWorker(QThread):
    finished = Signal(str, list, dict)
    error = Signal(str, str)

    def __init__(self, image_path: str, full_prompt: str, provider: str, model_name: str, api_key: str = "", ollama_url: str = "", ollama_token: str = ""):
        super().__init__()
        self.image_path = image_path
        self.full_prompt = full_prompt
        self.provider = provider
        self.model_name = model_name
        self.api_key = api_key
        self.ollama_url = ollama_url
        self.ollama_token = ollama_token

    def run(self):
        try:
            bubbles, usage = AIClientManager.execute_translation_request(
                image_path=self.image_path,
                prompt=self.full_prompt,
                provider=self.provider,
                model=self.model_name,
                api_key=self.api_key,
                endpoint_url=self.ollama_url,
                token=self.ollama_token
            )
            self.finished.emit(self.image_path, bubbles, usage)
        except Exception as e:
            logger.error(f"[AI_WORKER] Fallo la traduccion para {self.image_path}: {e}")
            self.error.emit(self.image_path, str(e))