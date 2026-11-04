"""Free LLM route: Gemini via the registered connector helper.

The helper uses curl (proxy-safe on this VM). Model preference order:
gemini-3.8-flash (best instruction-following) -> gemma-4-26b-a4b-it ->
gemma-4-31b-it. The Gemma models tend to "think out loud" (echoing the
instructions as a bullet outline before the real content), so callers
validate with looks_clean() and fall back to deterministic templates.

Returns the reply text, or None when all models fail / quota is out.
"""
import subprocess

from . import config

MODELS = ["gemini-3.8-flash", "gemma-4-26b-a4b-it", "gemma-4-31b-it"]


def _call(model, prompt, max_tokens):
    try:
        proc = subprocess.run(
            [
                "python3",
                config.GEMINI_HELPER,
                "generate",
                "--model",
                model,
                "--prompt",
                prompt,
                "--max-tokens",
                str(max_tokens),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as e:
        print(f"[llm] {model}: subprocess failed: {e}")
        return None
    out = (proc.stdout or "").strip()
    if not out:
        print(f"[llm] {model}: empty output")
        return None
    if out.startswith('{"error"') or out.startswith("{'error'"):
        print(f"[llm] {model}: provider error: {out[:140]}")
        return None
    return out


def ask(prompt, max_tokens=600):
    """Try each model in order. Returns (text, model) or (None, None)."""
    for model in MODELS:
        out = _call(model, prompt, max_tokens)
        if out:
            return out, model
    return None, None


def looks_clean(text, must_contain=None):
    """Reject Gemma-style echoed outlines: leading bullet/meta lines."""
    if not text:
        return False
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return False
    first = lines[0].strip()
    # Echoed thinking starts with bullets or meta labels
    if first.startswith(("*", "-", "\u2022")):
        return False
    low = first.lower()
    if any(k in low for k in ("constraint", "input:", "target audience",
                              "role:", "here is", "output:")):
        return False
    if must_contain and must_contain.lower() not in text.lower():
        return False
    return True
