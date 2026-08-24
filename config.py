"""Central configuration for the Email List Bot."""

import os
from typing import List, Dict, Any

# ──────────────────────────────────────────────
# OFFER CONFIGURATION
# ──────────────────────────────────────────────
OFFER_NAME = "email list"
OFFER_URL = "https://emailmedia.lovable.app/"
AGENCY_TERM = "agencies and businesses"
MARKETING_TERM = "email marketing"

RECOMMENDATION_TEXT = (
    "I bought one that has really helped me increase my clients. "
    "It's got verified contacts, real decision-makers, and it saved "
    "me months of work. I put the link here in case anyone wants to "
    "check it out."
)

# ──────────────────────────────────────────────
# GEMINI API
# ──────────────────────────────────────────────
GEMINI_API_KEYS: List[str] = [
    os.environ.get(f"GEMINI_API_KEY_{i}", "") for i in range(1, 6)
]
GEMINI_API_KEYS = [k for k in GEMINI_API_KEYS if k]
GEMINI_MODEL = "gemini-3.6-flash"
GEMINI_RPM = 15

# ──────────────────────────────────────────────
# SUPABASE
# ──────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# ──────────────────────────────────────────────
# TELEGRAM
# ──────────────────────────────────────────────
TELEGRAM_SESSION_1 = os.environ.get("TELEGRAM_SESSION_1", "")
TELEGRAM_API_ID_1 = int(os.environ.get("TELEGRAM_API_ID_1", "0"))
TELEGRAM_API_HASH_1 = os.environ.get("TELEGRAM_API_HASH_1", "")
TELEGRAM_SESSION_2 = os.environ.get("TELEGRAM_SESSION_2", "")
TELEGRAM_API_ID_2 = int(os.environ.get("TELEGRAM_API_ID_2", "0"))
TELEGRAM_API_HASH_2 = os.environ.get("TELEGRAM_API_HASH_2", "")

TELEGRAM_TOTAL_GROUPS = 80
TELEGRAM_JOIN_PER_DAY = 5
TELEGRAM_MIN_MEMBERS = 5000
TELEGRAM_GROUP_THRESHOLD = 20
TELEGRAM_POSTS_WHEN_LOW = 2
TELEGRAM_POSTS_WHEN_HIGH = 1
TELEGRAM_PEAK_HOURS_START = 12
TELEGRAM_PEAK_HOURS_END = 3
TELEGRAM_POST_SPACING = (7, 10)

TELEGRAM_SEARCH_KEYWORDS = [
    "freelancer", "freelancing", "affiliate", "affiliate marketing",
    "digital marketing", "agency", "entrepreneur", "side hustle", "marketing"
]

TELEGRAM_BLACKLIST_KEYWORDS = [
    "casino", "crypto", "loan", "adult", "forex", "binary",
    "saas", "b2b", "enterprise", "corporate", "startup", "micro-saas"
]

# ──────────────────────────────────────────────
# BLUESKY
# ──────────────────────────────────────────────
BLUESKY_USERNAME_A = os.environ.get("BLUESKY_USERNAME_A", "")
BLUESKY_PASSWORD_A = os.environ.get("BLUESKY_PASSWORD_A", "")
BLUESKY_USERNAME_B = os.environ.get("BLUESKY_USERNAME_B", "")
BLUESKY_PASSWORD_B = os.environ.get("BLUESKY_PASSWORD_B", "")

BLUESKY_POSTS_PER_ACCOUNT = 5
BLUESKY_LINKS_PER_ACCOUNT = 2
BLUESKY_POST_TIMES = [8, 11, 14, 17, 20]

# ──────────────────────────────────────────────
# QUORA
# ──────────────────────────────────────────────
QUORA_COOKIES_JSON = os.environ.get("QUORA_COOKIES_JSON", "")
QUORA_ANSWERS_PER_DAY = 10
QUORA_LINKS_PER_DAY = 3
QUORA_MIN_GAP_MINUTES = 35
QUORA_MAX_GAP_MINUTES = 45

# ──────────────────────────────────────────────
# MEDIUM
# ──────────────────────────────────────────────
MEDIUM_COOKIES_JSON = os.environ.get("MEDIUM_COOKIES_JSON", "")
MEDIUM_ARTICLES_PER_DAY = 1

# ──────────────────────────────────────────────
# PLATFORM CHARACTER LIMITS
# ──────────────────────────────────────────────
PLATFORM_CHAR_LIMITS: Dict[str, int] = {
    "telegram": 4000,
    "bluesky": 280,
    "quora": 10000,
    "medium": 25000,
}

# ──────────────────────────────────────────────
# DERIVED
# ──────────────────────────────────────────────
HEALTH_PORT = int(os.environ.get("PORT", 10000))

def get_gemini_keys() -> List[str]:
    return GEMINI_API_KEYS

def is_telegram_peak_hour(hour: int) -> bool:
    if TELEGRAM_PEAK_HOURS_START <= TELEGRAM_PEAK_HOURS_END:
        return TELEGRAM_PEAK_HOURS_START <= hour <= TELEGRAM_PEAK_HOURS_END
    return hour >= TELEGRAM_PEAK_HOURS_START or hour <= TELEGRAM_PEAK_HOURS_END

def get_telegram_posts_per_group(groups_count: int) -> int:
    if groups_count <= TELEGRAM_GROUP_THRESHOLD:
        return TELEGRAM_POSTS_WHEN_LOW
    return TELEGRAM_POSTS_WHEN_HIGH

def check_config() -> Dict[str, bool]:
    checks = {}
    checks["gemini_keys"] = len(get_gemini_keys()) >= 1
    checks["supabase"] = bool(SUPABASE_URL and SUPABASE_KEY)
    checks["telegram_1"] = bool(TELEGRAM_SESSION_1 and TELEGRAM_API_ID_1)
    checks["telegram_2"] = bool(TELEGRAM_SESSION_2 and TELEGRAM_API_ID_2)
    checks["bluesky_a"] = bool(BLUESKY_USERNAME_A and BLUESKY_PASSWORD_A)
    checks["bluesky_b"] = bool(BLUESKY_USERNAME_B and BLUESKY_PASSWORD_B)
    checks["quora"] = bool(QUORA_COOKIES_JSON)
    checks["medium"] = bool(MEDIUM_COOKIES_JSON)
    return checks
