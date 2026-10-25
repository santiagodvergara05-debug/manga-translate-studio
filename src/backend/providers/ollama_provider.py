import time
import requests
from src.backend.providers.base_provider import (
    BaseAIProvider, 
    TranslationResult, 
    ProviderStatus,
    DailyQuotaExceeded
)

# Standard transient HTTP status codes eligible for automatic retries
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class OllamaProvider(BaseAIProvider):
    """
    Provider implementation for Ollama API instances.
    
    Supports both:
    1. Local native daemon (e.g., http://localhost:11434 via /api/generate)
    2. Cloud / OpenAI-compatible reverse proxies (e.g., https://ollama.com/v1 via /chat/completions)
    """

    def __init__(self):
        super().__init__("ollama")

    @staticmethod
    def normalize_url(url: str, default: str = "https://ollama.com/v1") -> str:
        """
        Normalizes and formats the target endpoint URL.
        
        Ensures a proper protocol scheme (http:// for local subnets, https:// otherwise)
        and strips trailing slashes to ensure consistent endpoint concatenation.
        """
        clean = url.strip() if url else default
        if not clean:
            clean = default
            
        if not clean.startswith("http://") and not clean.startswith("https://"):
            # Automatically assign plain HTTP to standard local loopback and private subnets
            if any(local in clean.lower() for local in ("localhost", "127.0.0.1", "192.168.", "10.", "172.")):
                clean = f"http://{clean}"
            else:
                clean = f"https://{clean}"
                
        return clean.rstrip("/")

    def test_and_fetch_models(self, key_or_url: str, auth_token: str = "") -> tuple[bool, list[str], str]:
        """
        Validates connectivity and queries available models from the target Ollama instance.
        
        Attempts probing both the OpenAI-compatible (/v1/models) endpoint and 
        the native Ollama daemon endpoint (/api/tags).
        
        Returns:
            tuple[bool, list[str], str]: (success_flag, list_of_model_names, status_message)
        """
        base_url = self.normalize_url(key_or_url)
        token = auth_token.strip()
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        try:
            # 1. Probe cloud or proxy endpoint (/v1)
            if base_url.endswith("/v1"):
                res = requests.get(f"{base_url}/models", headers=headers, timeout=10)
                if res.status_code == 200:
                    models = [m.get("id") for m in res.json().get("data", []) if m.get("id")]
                    if models:
                        return True, models, "Connected to Ollama Cloud (/v1)."
                elif res.status_code in (401, 403):
                    return False, [], "Invalid or missing Ollama Cloud API Key."

            # 2. Probe native local Ollama daemon (/api/tags)
            try:
                res_local = requests.get(f"{base_url}/api/tags", headers=headers, timeout=8)
                if res_local.status_code == 200:
                    models = [m.get("name") for m in res_local.json().get("models", []) if m.get("name")]
                    if models:
                        return True, models, "Connected to Local Ollama."
            except Exception:
                pass

            # 3. Fallback attempt against /models route
            res_fb = requests.get(f"{base_url}/models", headers=headers, timeout=8)
            if res_fb.status_code == 200:
                models = [m.get("id") for m in res_fb.json().get("data", []) if m.get("id")]
                if models:
                    return True, models, "Connected to Ollama."

            return False, [], f"Could not retrieve models from {base_url}."
            
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
        """
        Executes a multimodal translation inference request via Ollama.
        
        Dispatches payload based on endpoint type:
        - OpenAI-compatible JSON schema mode for endpoints ending in '/v1'
        - Native Ollama /api/generate mode with Base64 image payload for local daemons
        
        Returns:
            TranslationResult: Standardized container holding status, parsed bubbles, and telemetry.
        """
        b64_img = self.encode_image(image_path)
        base_url = self.normalize_url(endpoint_url)
        usage_info = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        
        headers = {"Content-Type": "application/json"}
        if token.strip():
            headers["Authorization"] = f"Bearer {token.strip()}"

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                # Execution Branch A: OpenAI-compatible API format (/v1/chat/completions)
                if base_url.endswith("/v1"):
                    url = f"{base_url}/chat/completions"
                    payload = {
                        "model": model,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                            ]
                        }],
                        "temperature": 0.2,
                        "response_format": {"type": "json_object"}
                    }
                    res = requests.post(url, headers=headers, json=payload, timeout=120)
                    
                    # Handle Rate Limits (HTTP 429)
                    if res.status_code == 429:
                        body_err = res.text
                        if "quota" in body_err.lower() or "limit" in body_err.lower():
                            raise DailyQuotaExceeded("Monthly or daily quota exhausted on Ollama Cloud.")
                        if attempt < max_retries:
                            time.sleep(6 * (attempt + 1))
                            continue
                        return TranslationResult(
                            status=ProviderStatus.SERVER_BUSY,
                            usage=usage_info,
                            message="Rate limit reached (429). Retry in a few moments.",
                            raw_error=res.text[:120]
                        )
                        
                    # Handle transient server errors
                    if res.status_code in RETRYABLE_STATUS_CODES:
                        if attempt < max_retries:
                            time.sleep(4 * (attempt + 1))
                            continue
                        return TranslationResult(
                            status=ProviderStatus.SERVER_BUSY,
                            usage=usage_info,
                            message=f"Ollama server busy or unavailable ({res.status_code}).",
                            raw_error=res.text[:120]
                        )
                        
                    res.raise_for_status()

                    res_json = res.json()
                    raw_text = res_json["choices"][0]["message"]["content"]
                    parsed = self.clean_json_response(raw_text)
                    bubbles = self.normalize_bubbles(parsed)

                    u = res_json.get("usage", {})
                    p_tok = u.get("prompt_tokens", 0)
                    c_tok = u.get("completion_tokens", 0)
                    usage_info = {"prompt_tokens": p_tok, "output_tokens": c_tok, "total_tokens": p_tok + c_tok}

                # Execution Branch B: Native Ollama daemon format (/api/generate)
                else:
                    url = f"{base_url}/api/generate"
                    payload = {
                        "model": model,
                        "prompt": prompt,
                        "images": [b64_img],
                        "stream": False,
                        "format": "json",
                        "options": {"num_ctx": 8192, "temperature": 0.2}
                    }
                    res = requests.post(url, headers=headers, json=payload, timeout=120)
                    
                    if res.status_code in RETRYABLE_STATUS_CODES:
                        if attempt < max_retries:
                            time.sleep(4 * (attempt + 1))
                            continue
                        return TranslationResult(
                            status=ProviderStatus.SERVER_BUSY,
                            usage=usage_info,
                            message=f"Local Ollama instance busy or unresponsive ({res.status_code}).",
                            raw_error=res.text[:120]
                        )
                        
                    res.raise_for_status()

                    res_json = res.json()
                    raw_text = res_json.get("response", "{}")
                    parsed = self.clean_json_response(raw_text)
                    bubbles = self.normalize_bubbles(parsed)

                    p_tok = res_json.get("prompt_eval_count", 0)
                    c_tok = res_json.get("eval_count", 0)
                    usage_info = {"prompt_tokens": p_tok, "output_tokens": c_tok, "total_tokens": p_tok + c_tok}

                # Validate whether text entities were extracted
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
                # Handle inference timeouts when the local GPU/CPU is saturated
                if attempt < max_retries:
                    time.sleep(4 * (attempt + 1))
                    continue
                return TranslationResult(
                    status=ProviderStatus.SERVER_BUSY,
                    usage=usage_info,
                    message="Ollama request timed out (>120s). Local engine is saturated, retry later.",
                    raw_error="Read timed out (120s)"
                )
                
            except Exception as e:
                if attempt == max_retries:
                    return TranslationResult(
                        status=ProviderStatus.ERROR,
                        usage=usage_info,
                        message=f"Ollama execution failed: {str(e)}",
                        raw_error=str(e)
                    )
                time.sleep(3)

        return TranslationResult(status=ProviderStatus.ERROR, message="Unexpected termination in Ollama provider.")