"""Keep alive to prevent Render spin-down."""

import logging
import threading
import time
import requests
import os

logger = logging.getLogger(__name__)

class KeepAlive:
    def __init__(self):
        self.running = False
        self._thread = None

    def start(self):
        if self.running:
            return

        render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
        if not render_url:
            logger.warning("No Render URL, skipping keep-alive")
            return

        self.url = f"{render_url}/ping"
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Keep-alive started")

    def _run(self):
        while self.running:
            try:
                requests.get(self.url, timeout=10)
            except Exception as e:
                logger.warning(f"Keep-alive error: {e}")
            time.sleep(300)  # 5 minutes
