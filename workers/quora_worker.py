"""Quora worker — fully debugged."""

import json
import logging
import time
import random
import hashlib
from datetime import datetime, timezone

from patchright.sync_api import sync_playwright

from config import (
    QUORA_COOKIES_JSON, QUORA_ANSWERS_PER_DAY,
    QUORA_LINKS_PER_DAY, QUORA_MIN_GAP_MINUTES,
    QUORA_MAX_GAP_MINUTES, OFFER_URL,
)
from supabase_client import SupabaseClient
from content_generator import generate_content

logger = logging.getLogger(__name__)

class QuoraWorker:
    def __init__(self, supabase: SupabaseClient):
        self.supabase = supabase
        self.browser = None
        self.context = None
        self.page = None
        self.running = False

    def _get_cookies(self):
        if not QUORA_COOKIES_JSON:
            return []
        try:
            return json.loads(QUORA_COOKIES_JSON)
        except:
            return []

    def start(self) -> bool:
        for attempt in range(3):
            try:
                cookies = self._get_cookies()
                if not cookies:
                    return False

                playwright = sync_playwright().start()
                self.browser = playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                self.context = self.browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/127.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                    timezone_id="America/New_York",
                )
                self.context.add_cookies(cookies)
                self.page = self.context.new_page()

                self.page.goto("https://www.quora.com/profile", timeout=30000)
                time.sleep(3)

                if "login" in self.page.url.lower() or "signup" in self.page.url.lower():
                    self.supabase.update_worker_state("quora", {"status": "PAUSED", "last_error": "Cookies expired"})
                    return False

                self.running = True
                logger.info("Quora worker started")
                return True

            except Exception as e:
                logger.error(f"Quora start error (attempt {attempt + 1}): {e}")
                if attempt < 2:
                    time.sleep(10 * (attempt + 1))

        return False

    def _find_questions(self):
        if not self.page:
            return []

        questions = []
        topics = ["freelancing", "affiliate-marketing", "email-marketing", "small-business"]

        for topic in topics:
            try:
                self.page.goto(f"https://www.quora.com/topic/{topic}/questions", timeout=30000)
                time.sleep(3)

                for _ in range(2):
                    self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1)

                links = self.page.query_selector_all("a.question_link")
                for link in links[:5]:
                    href = link.get_attribute("href")
                    text = link.inner_text()
                    if href and text and "?" in text:
                        questions.append({
                            "url": f"https://www.quora.com{href}" if href.startswith("/") else href,
                            "title": text[:100],
                        })
            except Exception as e:
                logger.warning(f"Question search error: {e}")

        return questions

    def _write_answer(self, question_url: str, answer: str) -> bool:
        if not self.page:
            return False

        try:
            self.page.goto(question_url, timeout=30000)
            time.sleep(random.uniform(3, 5))

            # Check CAPTCHA
            if "captcha" in self.page.content().lower():
                self.supabase.update_worker_state("quora", {"status": "PAUSED", "last_error": "CAPTCHA detected"})
                return False

            # Find and click answer button
            for selector in ["button.WriteAnswerButton", "button:has-text('Answer')", "button:has-text('Write answer')"]:
                btn = self.page.query_selector(selector)
                if btn:
                    btn.click()
                    break

            time.sleep(2)

            # Find editor
            editor = None
            for selector in ["div[contenteditable='true']", "div.q-text.qu-contentEditable", "div.ProseMirror"]:
                editor = self.page.query_selector(selector)
                if editor:
                    break

            if not editor:
                logger.warning("Quora editor not found")
                return False

            editor.click()
            editor.fill(answer)
            time.sleep(1)

            # Submit
            for selector in ["button[type='submit']", "button:has-text('Submit Answer')", "button:has-text('Post')"]:
                btn = self.page.query_selector(selector)
                if btn:
                    btn.click()
                    break

            time.sleep(3)
            logger.info(f"Answer posted: {question_url[:50]}...")
            return True

        except Exception as e:
            logger.error(f"Answer error: {e}")
            return False

    def run_once(self) -> int:
        if not self.running and not self.start():
            return 0

        self.supabase.reset_daily_counters()
        state = self.supabase.get_worker_state("quora")
        today_count = state.get("today_count", 0)
        links_today = state.get("links_today", 0)

        if today_count >= QUORA_ANSWERS_PER_DAY or state.get("status") == "PAUSED":
            return 0

        questions = self._find_questions()
        if not questions:
            return 0

        q = random.choice(questions)
        with_link = links_today < QUORA_LINKS_PER_DAY and random.random() < 0.4

        audience = "freelancer" if random.random() < 0.5 else "affiliate"
        content = generate_content("quora", audience, with_link, q["title"])
        content_hash = hashlib.md5(content.encode()).hexdigest()

        if self.supabase.is_content_posted(content_hash):
            return 0

        if self._write_answer(q["url"], content):
            self.supabase.mark_content_posted(content_hash, "quora")
            self.supabase.update_worker_state("quora", {
                "today_count": today_count + 1,
                "links_today": links_today + (1 if with_link else 0),
            })
            time.sleep(random.randint(QUORA_MIN_GAP_MINUTES, QUORA_MAX_GAP_MINUTES) * 60)
            return 1

        return 0

    def run(self):
        logger.info("🚀 Starting Quora worker")
        while True:
            try:
                current_hour = datetime.now(timezone.utc).hour
                if 13 <= current_hour <= 20:
                    self.run_once()
                time.sleep(60)
            except Exception as e:
                logger.error(f"Quora error: {e}")
                time.sleep(60)
