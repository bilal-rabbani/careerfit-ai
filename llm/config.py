# One place to edit when models change. Verify names in each provider's console.
NODE_SLOTS = {
    "jd_parser": 0, "cv_parser": 1,
    "matcher_a": 2, "matcher_b": 3,
    "enhancer": 4, "summary": 5,
}

DEFAULT_MODELS = {
    "groq": "openai/gpt-oss-120b",
    "gemini": "gemini-3.8-flash",
}

REQUEST_TIMEOUT = 60        # seconds per HTTP call
MAX_RATE_LIMIT_WAIT = 20    # max seconds to wait if every key is rate limited

MAX_TOTAL_WAIT = 75        # seconds one call may spend waiting out rate limits
DEFAULT_COOLDOWN = 15      # used when the provider gives no retry hint
MAX_COOLDOWN = 45          # longest single wait
MAX_RATE_LIMIT_TRIES = 3   # rate-limited attempts per key before giving up on it
