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
