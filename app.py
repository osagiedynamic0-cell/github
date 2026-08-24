"""Main entry point."""

import os
import sys
import logging
import threading
from datetime import datetime, timezone

from flask import Flask, jsonify

from config import HEALTH_PORT
from supabase_client import SupabaseClient
from utils.health import HealthCheck
from utils.keep_alive import KeepAlive
from workers.telegram_worker import TelegramWorker
from workers.bluesky_worker import BlueskyWorker
from workers.quora_worker import QuoraWorker
from workers.medium_worker import MediumWorker

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Suppress noisy logs
for lib in ["httpx", "urllib3", "telethon"]:
    logging.getLogger(lib).setLevel(logging.WARNING)

app = Flask(__name__)

# Initialize
supabase = SupabaseClient()
health_check = HealthCheck(supabase)
keep_alive = KeepAlive()
workers = {}
boot_complete = False
boot_time = None

@app.route("/")
def index():
    return jsonify({
        "app": "Email List Bot",
        "status": "running",
        "boot_time": boot_time.isoformat() if boot_time else None,
        "health": "/health"
    })

@app.route("/ping")
def ping():
    return jsonify({"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()})

@app.route("/health")
def health():
    worker_status = {}
    for name, worker in workers.items():
        state = supabase.get_worker_state(name)
        worker_status[name] = {
            "status": state.get("status", "UNKNOWN"),
            "today_count": state.get("today_count", 0),
            "last_error": state.get("last_error", ""),
        }

    checks = {}
    for name, (passed, msg) in health_check.results.items():
        checks[name] = {"ok": passed, "detail": msg}

    all_ok = all(c.get("ok", False) for c in checks.values())

    return jsonify({
        "status": "✅ ALL OK" if all_ok else "⚠️ ISSUES",
        "boot_self_test_passed": boot_complete,
        "workers_running": len(workers),
        "workers": worker_status,
        "checks": checks,
    })

def run_worker(worker_class, name):
    supabase.update_worker_state(name, {"status": "RUNNING"})
    worker = worker_class(supabase)
    workers[name] = worker
    worker.run()

def startup():
    global boot_complete, boot_time

    boot_time = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("Email List Bot - Starting up")
    logger.info("=" * 60)

    logger.info("Running boot self-test...")
    boot_complete = health_check.run_all()

    if not boot_complete:
        logger.warning("Boot self-test had failures - starting anyway with degraded mode")

    logger.info("Starting worker threads...")

    worker_threads = [
        threading.Thread(target=run_worker, args=(TelegramWorker, "telegram"), daemon=True),
        threading.Thread(target=run_worker, args=(BlueskyWorker, "bluesky"), daemon=True),
        threading.Thread(target=run_worker, args=(QuoraWorker, "quora"), daemon=True),
        threading.Thread(target=run_worker, args=(MediumWorker, "medium"), daemon=True),
    ]

    for t in worker_threads:
        t.start()

    keep_alive.start()
    logger.info("Startup complete")

# Start in background
startup_thread = threading.Thread(target=startup, daemon=True)
startup_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=HEALTH_PORT, debug=False)
