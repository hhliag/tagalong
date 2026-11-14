"""One function for every LLM call: ask_json(stage, prompt, images=[], schema=None) -> dict.

Providers: gemini, anthropic, openai (any OpenAI-compatible base URL), offline (a person or
Claude Code writes the response file by hand). Keys and model come from .env.
"""
import base64
import json
import mimetypes
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from app import config  # noqa: F401  (loads .env)
from .common import PipelineError

PROVIDERS = ["gemini", "anthropic", "openai", "offline"]
MAX_TOKENS = 16000


class OfflineWaiting(Exception):
    def __init__(self, path):
        super().__init__(str(path))
        self.path = path


_ctx = {"provider": "offline", "model": None, "run_dir": None, "counters": {}}


def configure(provider, model, run_dir):
    if provider not in PROVIDERS:
        raise PipelineError(f"Unknown provider {provider!r}. Choose one of {PROVIDERS}.")
    _ctx.update(provider=provider, model=model, run_dir=Path(run_dir), counters={})


def provider():
    return _ctx["provider"]


def parse_json(text):
    """Parse a JSON object from a reply that may be wrapped in ``` fences or short prose."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object found in the reply")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("the reply is not a JSON object")
    return data


def _next_n(stage):
    _ctx["counters"][stage] = _ctx["counters"].get(stage, 0) + 1
    return _ctx["counters"][stage]


def _log(stage, n, kind, text):
    log_dir = _ctx["run_dir"] / "llm_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (log_dir / f"{stamp}_{stage}_{n}_{kind}").write_text(text, encoding="utf-8")


def ask_json(stage, prompt, images=(), schema=None):
    if schema is not None:
        prompt = f"{prompt}\n\nReturn JSON matching this schema:\n{json.dumps(schema, indent=2)}"
    images = [Path(i) for i in images]

    if _ctx["provider"] == "offline":
        return _offline(stage, _next_n(stage), prompt, images)

    n = _next_n(stage)
    reply = _call_logged(stage, n, prompt, images)
    try:
        return parse_json(reply)
    except ValueError as e:  # json.JSONDecodeError is a ValueError
        retry = (f"{prompt}\n\nYour previous reply could not be parsed as JSON ({e}). "
                 "Reply again with the JSON object only.")
        reply = _call_logged(stage, _next_n(stage), retry, images)
        try:
            return parse_json(reply)
        except ValueError as e2:
            raise PipelineError(f"{stage}: the LLM did not return valid JSON twice ({e2}). See llm_log/.") from e2


def _call_logged(stage, n, prompt, images):
    _log(stage, n, "request.md", _request_text(prompt, images))
    try:
        reply = _call(prompt, images)
    except PipelineError:
        raise
    except Exception as e:  # SDK errors: auth, timeout, rate limit, network
        _log(stage, n, "error.txt", repr(e))
        raise PipelineError(f"{stage}: {_ctx['provider']} call failed: {e}") from e
    _log(stage, n, "response.txt", reply)
    return reply


def _request_text(prompt, images, response_path=None):
    lines = [f"# Request ({_ctx['provider']}, model {_ctx['model'] or '-'})", ""]
    if response_path:
        lines += [
            "Act as the LLM for this request. Read the prompt below and every image listed.",
            "Follow the prompt's rules exactly. Write ONLY the JSON object it asks for to:",
            "", f"    {response_path}", "",
        ]
    if images:
        lines += ["## Images", ""] + [f"- {p.resolve()}" for p in images] + [""]
    lines += ["## Prompt", "", prompt, ""]
    return "\n".join(lines)


def _offline(stage, n, prompt, images):
    off = _ctx["run_dir"] / "offline"
    off.mkdir(parents=True, exist_ok=True)
    copies = []
    for img in images:
        dest = off / f"{stage}_{n}_{img.name}"
        shutil.copy2(img, dest)
        copies.append(dest)
    response = off / f"{stage}_{n}_response.json"
    request_text = _request_text(prompt, copies, response.resolve())
    (off / f"{stage}_{n}_request.md").write_text(request_text, encoding="utf-8")
    if not response.is_file():
        _log(stage, n, "request.md", request_text)
        raise OfflineWaiting(response.resolve())
    text = response.read_text(encoding="utf-8")
    _log(stage, n, "response.txt", text)
    try:
        return parse_json(text)
    except ValueError as e:
        raise PipelineError(f"{response} is not valid JSON ({e}). Fix the file and run again.") from e


# ---------- live providers ----------

def _timeout():
    return float(os.environ.get("STAGE_TIMEOUT") or 40)


def _key(name):
    key = os.environ.get(name)
    if not key:
        raise PipelineError(f"{name} is not set in .env (provider {_ctx['provider']}).")
    return key


def _model():
    if not _ctx["model"]:
        raise PipelineError("No model name: set LLM_MODEL in .env or pass --model NAME.")
    return _ctx["model"]


def _mime(path):
    return mimetypes.guess_type(path.name)[0] or "image/png"


def _call(prompt, images):
    p = _ctx["provider"]
    if p == "gemini":
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=_key("GEMINI_API_KEY"),
                              http_options=types.HttpOptions(timeout=int(_timeout() * 1000)))
        parts = [types.Part.from_bytes(data=i.read_bytes(), mime_type=_mime(i)) for i in images]
        resp = client.models.generate_content(
            model=_model(), contents=parts + [prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return resp.text or ""

    if p == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=_key("ANTHROPIC_API_KEY"), timeout=_timeout())
        content = [{"type": "image", "source": {"type": "base64", "media_type": _mime(i),
                                                 "data": base64.b64encode(i.read_bytes()).decode()}}
                   for i in images]
        content.append({"type": "text", "text": prompt})
        resp = client.messages.create(model=_model(), max_tokens=MAX_TOKENS,
                                      messages=[{"role": "user", "content": content}])
        return "".join(b.text for b in resp.content if b.type == "text")

    if p == "openai":
        import openai
        client = openai.OpenAI(api_key=_key("OPENAI_API_KEY"),
                               base_url=os.environ.get("OPENAI_BASE_URL") or None, timeout=_timeout())
        content = [{"type": "text", "text": prompt}]
        content += [{"type": "image_url", "image_url": {
            "url": f"data:{_mime(i)};base64,{base64.b64encode(i.read_bytes()).decode()}"}} for i in images]
        resp = client.chat.completions.create(model=_model(), messages=[{"role": "user", "content": content}],
                                              response_format={"type": "json_object"})
        return resp.choices[0].message.content or ""

    raise PipelineError(f"Unknown provider {p!r}")
