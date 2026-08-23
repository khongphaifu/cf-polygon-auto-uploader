import json
import re
import time
from typing import Any, Dict, Optional, List
import requests


class LLMClient:
    """Client for interacting with Google Gemini API with seamless multi-model fallback."""

    FALLBACK_MODELS = [
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
    ]

    def __init__(
        self,
        api_key: Any,
        backup_keys: Optional[List[str]] = None,
        model_name: str = "gemini-3.5-flash-lite",
        temperature: float = 0.2,
    ):
        self.api_keys_pool: List[str] = []
        if isinstance(api_key, list):
            self.api_keys_pool.extend([k.strip() for k in api_key if k and isinstance(k, str) and k.strip()])
        elif isinstance(api_key, str) and api_key.strip():
            self.api_keys_pool.append(api_key.strip())
        
        if backup_keys:
            for bk in backup_keys:
                if bk and isinstance(bk, str) and bk.strip() and bk.strip() not in self.api_keys_pool:
                    self.api_keys_pool.append(bk.strip())

        if not self.api_keys_pool:
            raise ValueError("No Gemini API key provided. Please configure gemini_api_key in config/config.yaml")

        self.api_key = self.api_keys_pool[0]
        # Default model alias normalization
        if model_name in ["gemini", "gemini-flash", "flash", "gemini-3.5-flash"]:
            self.model_name = "gemini-3.5-flash-lite"
        elif model_name in ["lite", "flash-lite"]:
            self.model_name = "gemini-3.5-flash-lite"
        else:
            self.model_name = model_name
        self.temperature = temperature
        self.session = requests.Session()

    def _clean_json_response(self, text: str) -> str:
        """Extract, clean and auto-repair raw JSON from LLM response."""
        text = text.strip()
        # Strip markdown ```json ... ```
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        
        # If still wrapped or containing extra text, find outermost { and }
        first_brace = text.find("{")
        if first_brace != -1:
            last_brace = text.rfind("}")
            if last_brace != -1 and last_brace > first_brace:
                text = text[first_brace:last_brace + 1]
            else:
                text = text[first_brace:]
                
        return text

    def _safe_json_loads(self, text: str) -> Dict[str, Any]:
        """Attempt to parse JSON with automatic truncation repair if needed."""
        cleaned = self._clean_json_response(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try basic auto-repair for truncated JSON: close open string and brackets
            repaired = cleaned
            quote_count = len(re.findall(r'(?<!\\)"', repaired))
            if quote_count % 2 == 1:
                repaired += '"'
            open_curly = repaired.count('{') - repaired.count('}')
            open_square = repaired.count('[') - repaired.count(']')
            if open_square > 0:
                repaired += ']' * open_square
            if open_curly > 0:
                repaired += '}' * open_curly
            try:
                return json.loads(repaired)
            except Exception:
                pass
            return json.loads(cleaned)

    def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model_override: Optional[str] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Send request to Gemini API with automatic API Key rotation and multi-model fallback.
        """
        chosen_model = model_override or self.model_name
        model_candidates: List[str] = [chosen_model]
        for m in self.FALLBACK_MODELS:
            if m not in model_candidates:
                model_candidates.append(m)

        last_error: Optional[Exception] = None

        # Iterate over all available API keys in the pool
        for current_key in self.api_keys_pool:
            # Try entire sequence of models up to 2 rounds per key
            for round_idx in range(2):
                if round_idx > 0:
                    time.sleep(8)  # Short cooldown between full passes

                for candidate_model in model_candidates:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent?key={current_key}"
                    
                    payload: Dict[str, Any] = {
                        "contents": [
                            {
                                "role": "user",
                                "parts": [{"text": prompt}],
                            }
                        ],
                        "generationConfig": {
                            "temperature": self.temperature,
                            "maxOutputTokens": 8192,
                            "responseMimeType": "application/json",
                        },
                        "safetySettings": [
                            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
                        ],
                    }

                    if system_instruction:
                        payload["systemInstruction"] = {
                            "parts": [{"text": system_instruction}]
                        }

                    for attempt in range(1, max_retries + 1):
                        try:
                            response = self.session.post(
                                url,
                                json=payload,
                                headers={"Content-Type": "application/json"},
                                timeout=90,
                            )
                            
                            if response.status_code == 200:
                                data = response.json()
                                candidates = data.get("candidates", [])
                                if not candidates:
                                    raise ValueError(f"No candidate generated by Gemini API: {data}")
                                
                                candidate = candidates[0]
                                finish_reason = candidate.get("finishReason")
                                parts = candidate.get("content", {}).get("parts", [])
                                if not parts:
                                    raise ValueError(f"Candidate has no parts (finishReason: {finish_reason})")

                                raw_text = parts[0].get("text", "")
                                return self._safe_json_loads(raw_text)
                            
                            elif response.status_code in [429, 503]:
                                last_error = RuntimeError(f"{candidate_model} returned HTTP {response.status_code} (busy/rate limit)")
                                if attempt < max_retries:
                                    time.sleep(4 * attempt)
                                else:
                                    break  # Switch to next candidate model
                            
                            elif response.status_code == 404:
                                last_error = RuntimeError(f"{candidate_model} returned 404 Not Found")
                                break  # Switch to next candidate model
                            
                            else:
                                last_error = RuntimeError(f"HTTP {response.status_code} on {candidate_model}: {response.text[:200]}")
                                time.sleep(2)
                        
                        except Exception as e:
                            last_error = e
                            if attempt < max_retries:
                                time.sleep(2)

        raise RuntimeError(f"Failed to generate content with Gemini API across all keys and models: {last_error}")

    def generate_from_image(
        self,
        prompt: str,
        image_bytes: bytes,
        mime_type: str = "image/png",
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Send multimodal vision request (image + prompt) to Gemini API with key rotation.
        """
        import base64

        img_b64 = base64.b64encode(image_bytes).decode("utf-8")
        chosen_model = self.model_name
        model_candidates = [chosen_model]
        for m in self.FALLBACK_MODELS:
            if m not in model_candidates:
                model_candidates.append(m)

        last_error = None
        for current_key in self.api_keys_pool:
            for candidate_model in model_candidates:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent?key={current_key}"
                payload = {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {"text": prompt},
                                {
                                    "inlineData": {
                                        "mimeType": mime_type,
                                        "data": img_b64,
                                    }
                                },
                            ],
                        }
                    ],
                    "generationConfig": {
                        "temperature": self.temperature,
                        "maxOutputTokens": 8192,
                        "responseMimeType": "application/json",
                    },
                }

                for attempt in range(1, max_retries + 1):
                    try:
                        response = self.session.post(
                            url,
                            json=payload,
                            headers={"Content-Type": "application/json"},
                            timeout=120,
                        )
                        if response.status_code == 200:
                            data = response.json()
                            candidates = data.get("candidates", [])
                            if not candidates:
                                raise ValueError("No candidate in multimodal response")
                            raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            return self._safe_json_loads(raw_text)
                        elif response.status_code in [429, 503]:
                            time.sleep(3 * attempt)
                        else:
                            break
                    except Exception as e:
                        last_error = e
                        time.sleep(2)

        raise RuntimeError(f"Failed to analyze image with Gemini Vision API: {last_error}")
