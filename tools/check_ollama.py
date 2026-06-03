"""Ollama connection diagnostic.

Usage:
    python3 -m tools.check_ollama

Walks the same connection pipeline the card generator uses, but prints every
step with timing and HTTP status so you can see exactly where it fails when
"nothing generates". Tests in order:

    1. Read host / model settings.
    2. Ping each candidate host (HTTP GET /api/tags) with a short timeout.
    3. On the first reachable host: list available models, check that the
       configured model is present.
    4. Send a tiny chat request end-to-end with the long LLM timeout.

Exit code 0 = ready to generate. Non-zero = something is broken; the script
tells you which step failed.
"""
from __future__ import annotations

import os
import sys
import time
import traceback

# Allow `python3 tools/check_ollama.py` (without -m) by adding repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- pretty printing -------------------------------------------------------

OK = "\033[92m✓\033[0m"
BAD = "\033[91m✗\033[0m"
WARN = "\033[93m!\033[0m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"


def _step(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}")


def _ok(msg: str) -> None:
    print(f"  {OK} {msg}")


def _bad(msg: str) -> None:
    print(f"  {BAD} {msg}")


def _warn(msg: str) -> None:
    print(f"  {WARN} {msg}")


def _dim(msg: str) -> None:
    print(f"  {DIM}{msg}{RESET}")


# --- diagnostic steps ------------------------------------------------------

def main() -> int:
    try:
        from data.db import init_db
        init_db()
        from data.settings_service import ensure_loaded, get_bool, get_int, get_str
        ensure_loaded()
    except Exception as exc:
        _bad(f"Failed to load settings: {exc}")
        traceback.print_exc()
        return 1

    # Step 1: read settings
    _step("1. Settings")
    use_ollama = get_bool("ai.use_ollama")
    model = get_str("ai.ollama_model")
    host_setting = get_str("ai.ollama_host")
    chat_timeout = get_int("ai.request_timeout")
    _dim(f"ai.use_ollama         = {use_ollama}")
    _dim(f"ai.ollama_host        = {host_setting!r}")
    _dim(f"ai.ollama_model       = {model!r}")
    _dim(f"ai.request_timeout    = {chat_timeout}s")
    if not use_ollama:
        _warn("ai.use_ollama is OFF — generator runs in template mode regardless of connectivity.")
    if not host_setting:
        _warn("ai.ollama_host is empty — will fall through to 127.0.0.1 / localhost.")
    if not model:
        _bad("ai.ollama_model is empty — set a model name in Settings → AI.")
        return 1
    _ok("Settings loaded.")

    # Step 2: ollama python module
    _step("2. Ollama Python module")
    try:
        import ollama  # noqa: F401
        _ok("`ollama` module importable.")
    except Exception as exc:
        _bad(f"`ollama` module not importable: {exc}")
        _dim("Install with: pip3 install ollama")
        return 1

    # Step 3: Wikipedia — needed even in template mode, because the pool walk
    # asks Wikipedia for each candidate person.
    _step("3. Wikipedia reachability (5 known summaries, 10s timeout each)")
    import requests
    from data.wikipedia import HEADERS
    test_titles = ["Albert Einstein", "Napoleon", "Confucius", "Marie Curie", "Mahatma Gandhi"]
    timings: list[float] = []
    wiki_failures = 0
    for title in test_titles:
        safe = title.replace(" ", "_")
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{safe}"
        t0 = time.time()
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            dt = (time.time() - t0) * 1000
            timings.append(dt)
            if r.status_code == 200:
                _ok(f"{title:18}  [{r.status_code} in {dt:.0f}ms]")
            else:
                wiki_failures += 1
                _bad(f"{title:18}  HTTP {r.status_code}  ({dt:.0f}ms)")
        except requests.RequestException as exc:
            dt = (time.time() - t0) * 1000
            wiki_failures += 1
            timings.append(dt)
            _bad(f"{title:18}  {type(exc).__name__}: {exc} ({dt:.0f}ms)")
    if timings:
        avg = sum(timings) / len(timings)
        _dim(f"avg {avg:.0f}ms over {len(timings)} requests")
        if avg > 3000 and wiki_failures == 0:
            _warn("Wikipedia is slow from this network — pool walk may take minutes per card.")
            _warn("Try disabling VPN, or split-tunnel en.wikipedia.org outside the tunnel.")
    if wiki_failures >= 3:
        _bad("Wikipedia is largely unreachable. Card generation will hang on pool walk.")

    # Step 4: ping every candidate Ollama host
    _step("4. Ollama host reachability (HTTP GET /api/tags, 3s timeout)")
    from data.ollama_gen_v2 import _host_candidates
    hosts = _host_candidates()
    reachable: list[str] = []
    for host in hosts:
        t0 = time.time()
        try:
            r = requests.get(f"{host}/api/tags", timeout=3)
            dt = (time.time() - t0) * 1000
            if r.status_code == 200:
                _ok(f"{host}  [{r.status_code} in {dt:.0f}ms]")
                reachable.append(host)
            else:
                _bad(f"{host}  HTTP {r.status_code} ({dt:.0f}ms)")
        except requests.RequestException as exc:
            dt = (time.time() - t0) * 1000
            _bad(f"{host}  {type(exc).__name__}: {exc} ({dt:.0f}ms)")

    if not reachable:
        _bad("No Ollama host responded. Check that:")
        _dim("  - The Ollama server is actually running (`ollama serve` on the host machine).")
        _dim("  - You're on the same network / VPN as the configured host.")
        _dim("  - Firewall isn't blocking port 11434.")
        return 1

    active_host = reachable[0]
    _step(f"5. Model availability on {active_host}")
    try:
        r = requests.get(f"{active_host}/api/tags", timeout=5)
        r.raise_for_status()
        models_json = r.json().get("models", []) or []
    except Exception as exc:
        _bad(f"Could not list models: {exc}")
        return 1
    names = sorted({m.get("name", "") for m in models_json if m.get("name")})
    if not names:
        _warn("Host responded but reported zero models. Pull a model with `ollama pull <name>`.")
        return 1
    if model not in names and not any(n.split(":")[0] == model for n in names):
        _bad(f"Configured model {model!r} is not installed on this host.")
        _dim(f"Available: {', '.join(names)}")
        _dim(f"Install with: ollama pull {model}")
        return 1
    _ok(f"Model {model!r} is installed.")
    _dim(f"Other models present: {', '.join(n for n in names if n != model) or '(none)'}")

    # Step 6: full end-to-end chat smoke test
    _step(f"6. Live chat smoke test (timeout {chat_timeout}s)")
    _dim("Sending: {'role':'user','content':'Reply with just OK.'}")
    t0 = time.time()
    try:
        import ollama
        client = ollama.Client(host=active_host, timeout=chat_timeout)
        resp = client.chat(
            model=model,
            messages=[{"role": "user", "content": "Reply with just OK."}],
            options={"temperature": 0.0},
        )
        dt = time.time() - t0
        content = (resp.get("message") or {}).get("content", "").strip()
        if content:
            _ok(f"Got reply in {dt:.1f}s: {content[:80]!r}")
        else:
            _warn(f"Reply was empty after {dt:.1f}s. Model may need more time on cold start.")
    except Exception as exc:
        dt = time.time() - t0
        _bad(f"Chat failed after {dt:.1f}s: {type(exc).__name__}: {exc}")
        if "timed out" in str(exc).lower() or isinstance(exc, TimeoutError):
            _dim("Increase Settings → Advanced → AI request timeout if the model is slow on first call.")
        return 1

    _step("All checks passed")
    _ok(f"Ollama at {active_host} is ready. Generator will use model {model!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
