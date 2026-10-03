
"""Scans staged files for likely secrets. Exit code 1 = blocked."""
import re, subprocess, sys

PATTERNS = {
    "GitHub token":      r"gh[pousr]_[A-Za-z0-9]{30,}",
    "GitHub fine-grained": r"github_pat_[A-Za-z0-9_]{30,}",
    "Groq key":          r"gsk_[A-Za-z0-9]{20,}",
    "Google API key":    r"AIza[0-9A-Za-z_\-]{30,}",
    "OpenAI-style key":  r"sk-[A-Za-z0-9]{20,}",
    "Hardcoded secret":  r"(?i)(api[_-]?key|token|secret|password)\s*[=:]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']",
}
BLOCKED_FILES = (".env", "secrets.toml")

files = subprocess.run("git diff --cached --name-only", shell=True,
                       capture_output=True, text=True).stdout.split()
bad = []
for f in files:
    if f.endswith(BLOCKED_FILES):
        bad.append((f, "secrets file staged"))
        continue
    try:
        text = open(f, encoding="utf-8", errors="ignore").read()
    except (FileNotFoundError, IsADirectoryError):
        continue
    for name, pat in PATTERNS.items():
        if re.search(pat, text):
            bad.append((f, name))

if bad:
    for f, why in bad:
        print(f"[!] {f}: {why}")
    sys.exit(1)
print("Secret scan passed.")
