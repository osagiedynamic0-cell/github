"""Gemini API client with 5-key round-robin."""

import time
import logging
import random
from typing import Optional, List
import google.generativeai as genai

from config import get_gemini_keys, GEMINI_MODEL, GEMINI_RPM

logger = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self):
        self.keys = get_gemini_keys()
        if not self.keys:
            raise RuntimeError("No Gemini API keys configured")
        self.key_index = 0
        self.model = GEMINI_MODEL
        self._last_request_time = 0.0
        self._min_interval = 60.0 / GEMINI_RPM
        self._key_cooldowns = {}

    def _rotate_key(self):
        self.key_index = (self.key_index + 1) % len(self.keys)

    def _rate_limit_wait(self):
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed + random.uniform(0.1, 0.5))
        self._last_request_time = time.time()

    def generate(self, prompt: str, platform: str = "general", max_retries: int = 3) -> str:
        last_error = None

        for attempt in range(max_retries * len(self.keys)):
            self._rate_limit_wait()

            key = self.keys[self.key_index]
            key_num = self.key_index + 1

            # Check cooldown
            if key in self._key_cooldowns and self._key_cooldowns[key] > time.time():
                self._rotate_key()
                continue

            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel(self.model)
                response = model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.8,
                        "top_p": 0.95,
                        "max_output_tokens": 8192,
                    }
                )

                if not response.text:
                    logger.warning(f"Empty response from Gemini key {key_num}, rotating")
                    self._rotate_key()
                    continue

                return response.text.strip()

            except Exception as e:
                error_str = str(e).lower()
                logger.warning(f"Gemini key {key_num} failed: {e}")
                last_error = e

                if "429" in error_str or "rate_limit" in error_str:
                    wait = min(60 * (attempt + 1), 300)
                    self._key_cooldowns[key] = time.time() + wait
                    logger.info(f"Rate limited on key {key_num}, cooling for {wait}s")
                    self._rotate_key()
                    continue

                if "not found" in error_str or "quota" in error_str:
                    self._rotate_key()
                    time.sleep(2)
                    continue

                if "timeout" in error_str:
                    time.sleep(5)
                    continue

                self._rotate_key()
                time.sleep(1)

        raise RuntimeError(f"All Gemini keys exhausted. Last error: {last_error}")

    def test_key(self, key_index: int) -> bool:
        try:
            key = self.keys[key_index]
            genai.configure(api_key=key)
            model = genai.GenerativeModel(self.model)
            response = model.generate_content("Say 'OK' if you can read this.")
            return bool(response.text)
        except Exception:
            return False

    def test_all_keys(self) -> List[bool]:
        return [self.test_key(i) for i in range(len(self.keys))]
