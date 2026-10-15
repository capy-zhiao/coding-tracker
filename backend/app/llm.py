"""Pluggable LLM layer: interview follow-ups, answer grading and complexity checks.

Two providers are supported and selected with LLM_PROVIDER:

  anthropic — Claude. Uses native structured outputs (`messages.parse`), so the response
              is already a validated Pydantic object. Best quality follow-ups.
  deepseek  — DeepSeek via its OpenAI-compatible API. Roughly 30x cheaper; JSON mode plus
              manual Pydantic validation, since it has no strict-schema equivalent.

Whose key: the server's own (LLM_PROVIDER and its key in .env) serves the owner — in local
mode that's the one local user. Anyone else brings their own key; it arrives with each
request (see config_from_headers) and is used for that request only, never stored, cached
or logged.

Design principle: **graceful degradation**. With LLM_PROVIDER=none (or a missing key) these
functions return empty results and the rest of the app keeps working — no hard dependency.
"""
from __future__ import annotations

import ast
import difflib
import ipaddress
import json
import logging
import re
import socket
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TypeVar
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, ValidationError

from .config import settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------- schemas
class FollowUpItem(BaseModel):
    question: str = Field(description="A follow-up question an interviewer would ask, one sentence")
    hint: str = Field(description="Key points a good answer should cover, two or three sentences")


class FollowUpBundle(BaseModel):
    followups: list[FollowUpItem]


class AnswerGrade(BaseModel):
    score: int = Field(ge=1, le=4, description="1 weak, 2 partial, 3 good, 4 strong")
    feedback: str = Field(description="One or two sentences, the way an interviewer would react")
    missing: list[str] = Field(
        description="Specific points the answer missed or got wrong, one sentence each; "
                    "empty list if none"
    )
    model_answer: str = Field(
        description="A strong answer, three or four sentences, phrased the way a candidate "
                    "would say it out loud"
    )


class ComplexityVerdict(BaseModel):
    """Laid out the way the result is read: right or wrong, why, the optimum, a faster version."""
    actual_time: str = Field(description="Big-O time of THIS code as written. Notation only, "
                                         "e.g. O(V + E) — no words")
    actual_space: str = Field(description="Big-O auxiliary space of THIS code. Notation only")
    time_correct: bool = Field(description="Does the candidate's stated time equal actual_time?")
    space_correct: bool = Field(description="Does the candidate's stated space equal actual_space?")
    why_wrong: str = Field(
        default="",
        description="Only if a stated answer is wrong: what the candidate missed and where "
                    "the real cost comes from, naming the variables — one or two sentences. "
                    "Empty string if both answers are correct.",
    )
    optimal_time: str = Field(description="Best known time for this problem. Notation only")
    optimal_space: str = Field(description="Space of that best-known solution. Notation only")
    time_optimal: bool = Field(description="Is this code's time already optimal? Equivalent "
                                           "notation counts as equal (O(n) = O(V) when n is "
                                           "the node count)")
    space_optimal: bool = Field(description="Is this code's space already optimal? Equivalent "
                                            "notation counts as equal")
    optimal_how: str = Field(
        default="",
        description="Only if time or space is not optimal: the technique that reaches the "
                    "optimum, one sentence. Empty string otherwise.",
    )
    optimized_code: str = Field(
        default="",
        description="Only if time or space is not optimal: the candidate's code with the "
                    "smallest change that reaches the optimum — same class, method signature, "
                    "variable names and style. Complete code as plain text, no markdown. "
                    "Empty string when already optimal in both.",
    )


def first_big_o(text: str) -> str:
    """The first O(...) in `text`, parentheses balanced — strips prose a model appends, as in
    "O(V+E) (or O(V) with early edge count check)". Returns "" if there is none."""
    i = (text or "").find("O(")
    if i == -1:
        return ""
    depth = 0
    for j in range(i + 1, len(text)):
        depth += text[j] == "("
        depth -= text[j] == ")"
        if depth == 0:
            return text[i:j + 1]
    return ""


def _is_placeholder(text: str) -> bool:
    """Empty, or filler like "..." / "N/A" — seen from flash on the relay."""
    t = (text or "").strip().strip(".").strip()
    return len(t) < 12 or t.lower() in {"n/a", "none", "todo"}


def verdict_problems(v: ComplexityVerdict) -> list[str]:
    """What is missing or malformed in a verdict; empty when it is complete."""
    issues = [f"{f} is not big-O notation" for f in
              ("actual_time", "actual_space", "optimal_time", "optimal_space")
              if not first_big_o(getattr(v, f))]
    if not (v.time_correct and v.space_correct) and _is_placeholder(v.why_wrong):
        issues.append("why_wrong missing for a wrong answer")
    if not (v.time_optimal and v.space_optimal) and _is_placeholder(v.optimal_how):
        issues.append("optimal_how missing for a non-optimal solution")
    return issues


def tidy_verdict(v: ComplexityVerdict) -> ComplexityVerdict:
    """Big-O fields reduced to notation; placeholder text blanked rather than displayed."""
    for f in ("actual_time", "actual_space", "optimal_time", "optimal_space"):
        setattr(v, f, first_big_o(getattr(v, f)) or getattr(v, f).strip())
    for f in ("why_wrong", "optimal_how"):
        if _is_placeholder(getattr(v, f)):
            setattr(v, f, "")
    return v


def extract_json(raw: str) -> str:
    """The most likely JSON object in a model reply (first candidate from json_candidates)."""
    found = json_candidates(raw)
    return found[0] if found else raw.strip()


def json_candidates(raw: str) -> list[str]:
    """Every JSON object in a reply, most likely first: fenced blocks, then balanced
    top-level {...} spans.

    JSON mode is documented for DeepSeek, but not in combination with thinking mode, and
    third-party relays vary. One relay was seen echoing the requested schema back before
    the real answer in a ```json fence — so a reply can hold several objects, and the
    caller keeps the first one that actually validates.
    """
    text = raw.strip()
    out = [m.group(1) for m in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)]
    depth, start, in_str, esc = 0, -1, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                out.append(text[start:i + 1])
    seen, unique = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def parse_reply(raw: str, schema: type[T]) -> T | None:
    """The first JSON object in `raw` that validates against `schema`, else None."""
    for candidate in json_candidates(raw):
        try:
            return schema.model_validate_json(candidate)
        except ValidationError:
            continue
    return None


def describe_fields(schema: type[BaseModel]) -> str:
    """A plain field list for the prompt. Pasting the raw JSON Schema invites a model to
    echo it back verbatim instead of filling it in."""
    js = schema.model_json_schema()
    lines = []
    for name, prop in js.get("properties", {}).items():
        kind = prop.get("type", "object")
        if kind == "array":
            kind = f"array of {prop.get('items', {}).get('type', 'object')}"
        if "minimum" in prop or "maximum" in prop:
            kind += f" ({prop.get('minimum', '')}..{prop.get('maximum', '')})"
        lines.append(f'- "{name}" ({kind}): {prop.get("description", "")}')
    return "\n".join(lines)


# ---------------------------------------------------------------- configuration
@dataclass(frozen=True)
class LLMConfig:
    """Everything a provider needs. Built from .env for the server's key, or from request
    headers for a user's own key."""
    provider: str                       # "deepseek" (any OpenAI-compatible API) | "anthropic"
    api_key: str = field(repr=False)    # never in a repr, so never in a log line
    model: str
    base_url: str = ""
    complexity_model: str = ""          # optional cheaper model for complexity checks
    thinking: bool | None = None        # None: send no thinking parameters at all
    reasoning_effort: str = ""
    complexity_effort: str = ""
    timeout: int = 300


def server_config() -> LLMConfig | None:
    """The server's own key from .env, or None when it has none."""
    choice = settings.llm_provider.strip().lower()
    if choice == "anthropic" and settings.anthropic_api_key:
        return LLMConfig("anthropic", settings.anthropic_api_key, settings.anthropic_model,
                         timeout=settings.llm_timeout_seconds)
    if choice == "deepseek" and settings.deepseek_api_key:
        return LLMConfig(
            "deepseek", settings.deepseek_api_key, settings.deepseek_model,
            base_url=settings.deepseek_base_url,
            complexity_model=settings.deepseek_complexity_model,
            thinking=settings.deepseek_thinking,
            reasoning_effort=settings.deepseek_reasoning_effort,
            complexity_effort=settings.deepseek_complexity_effort,
            timeout=settings.llm_timeout_seconds,
        )
    return None


# Request headers that carry a user's own key. The browser keeps the key and sends it only
# with AI requests; this server forwards it to the provider and forgets it.
HEADER_PROVIDER = "x-llm-provider"      # "openai" (any OpenAI-compatible API) | "anthropic"
HEADER_KEY = "x-llm-key"
HEADER_BASE_URL = "x-llm-base-url"
HEADER_MODEL = "x-llm-model"
DEFAULT_OPENAI_BASE_URL = "https://api.deepseek.com"


class BadKeyConfig(ValueError):
    """The user's AI settings can't be used as sent; the message says what to fix."""


def config_from_headers(headers: Mapping[str, str]) -> LLMConfig | None:
    """The caller's own provider settings, or None if the request carries no key."""
    key = (headers.get(HEADER_KEY) or "").strip()
    if not key:
        return None
    if len(key) > 500:
        raise BadKeyConfig("That API key is too long to be real")
    kind = (headers.get(HEADER_PROVIDER) or "openai").strip().lower()
    model = (headers.get(HEADER_MODEL) or "").strip()
    if not model:
        raise BadKeyConfig("Choose a model in Settings")
    if kind == "anthropic":
        return LLMConfig("anthropic", key, model, timeout=settings.llm_timeout_seconds)
    if kind != "openai":
        raise BadKeyConfig("Provider must be OpenAI-compatible or Anthropic")
    base_url = check_base_url((headers.get(HEADER_BASE_URL) or DEFAULT_OPENAI_BASE_URL).strip())
    # Other vendors reject DeepSeek's thinking parameters, so none are sent for user keys.
    return LLMConfig("deepseek", key, model, base_url=base_url,
                     timeout=settings.llm_timeout_seconds)


def check_base_url(url: str) -> str:
    """Accept only https URLs whose host resolves to public addresses.

    The server makes the request, so without this a user-supplied URL could point it at
    something only the server can reach: localhost, the private network, or the cloud
    metadata endpoint (169.254.169.254). A host that resolves differently later (DNS
    rebinding) could still slip past; the EC2 metadata service also requires IMDSv2's
    PUT-issued token, which this client never sends.
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise BadKeyConfig("The base URL must start with https://")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as e:
        raise BadKeyConfig(f"Can't find the host {parts.hostname}") from e
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise BadKeyConfig("The base URL must point at a public address")
    return url.rstrip("/")


# ---------------------------------------------------------------- providers
class _Provider:
    """Common interface so the rest of the app never cares which vendor is behind it."""

    name = "none"

    def model_for(self, task: str = "default") -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def complete(
        self, prompt: str, schema: type[T], task: str = "default",
    ) -> T | None:  # pragma: no cover - interface
        raise NotImplementedError


class AnthropicProvider(_Provider):
    name = "anthropic"

    def __init__(self, cfg: LLMConfig) -> None:
        import anthropic

        self.cfg = cfg
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=cfg.api_key, timeout=cfg.timeout)

    def model_for(self, task: str = "default") -> str:
        return self.cfg.model

    def complete(self, prompt: str, schema: type[T], task: str = "default") -> T | None:
        a = self._anthropic
        try:
            res = self._client.messages.parse(
                model=self.model_for(task),
                max_tokens=4000,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
            )
            return res.parsed_output
        except a.NotFoundError:
            log.warning("Anthropic: model not found or not accessible")
        except a.RateLimitError:
            log.warning("Anthropic: rate limited, try again later")
        except a.APIStatusError as e:
            log.warning("Anthropic: HTTP %s", e.status_code)
        except a.APIConnectionError:
            log.warning("Anthropic: could not reach the API")
        return None


class DeepSeekProvider(_Provider):
    """DeepSeek exposes an OpenAI-compatible endpoint, so we use the OpenAI SDK.

    It has JSON mode but no strict schema enforcement, so we embed the JSON schema in the
    prompt and validate the reply ourselves with Pydantic.
    """

    name = "deepseek"

    def __init__(self, cfg: LLMConfig) -> None:
        import openai

        self.cfg = cfg
        self._openai = openai
        self._client = openai.OpenAI(api_key=cfg.api_key, base_url=cfg.base_url,
                                     timeout=cfg.timeout)

    def request_options(self, task: str = "default") -> dict:
        """Thinking-mode parameters. They go in extra_body, which the SDK merges into the
        top level of the request JSON — reasoning_effort's values (low/high/max) are
        DeepSeek's own, so they are kept out of the SDK's typed arguments."""
        cfg = self.cfg
        if cfg.thinking is None:            # a user's own endpoint: send nothing extra
            return {"max_tokens": 16000}
        if cfg.thinking:
            return {
                "max_tokens": 16000,   # reasoning tokens count towards the limit
                "extra_body": {
                    "thinking": {"type": "enabled"},
                    "reasoning_effort": (
                        cfg.complexity_effort
                        if task == "complexity" and cfg.complexity_effort
                        else cfg.reasoning_effort
                    ),
                },
            }
        return {"max_tokens": 4000, "extra_body": {"thinking": {"type": "disabled"}}}

    def model_for(self, task: str = "default") -> str:
        if task == "complexity" and self.cfg.complexity_model:
            return self.cfg.complexity_model
        return self.cfg.model

    def complete(self, prompt: str, schema: type[T], task: str = "default") -> T | None:
        o = self._openai
        fields = describe_fields(schema)
        nested = ""
        for name, sub in schema.model_fields.items():
            item = getattr(sub.annotation, "__args__", (None,))[0]
            if isinstance(item, type) and issubclass(item, BaseModel):
                nested += f'\nEach element of "{name}" is an object with:\n{describe_fields(item)}'
        full = (
            f"{prompt}\n\n"
            f"Reply with ONE JSON object and nothing else — no markdown fences, no "
            f"commentary, do not repeat these instructions. Its keys:\n{fields}{nested}"
        )
        try:
            res = self._client.chat.completions.create(
                model=self.model_for(task),
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": full}],
                **self.request_options(task),
            )
            raw = res.choices[0].message.content or ""
            if getattr(res.choices[0], "finish_reason", None) == "length":
                log.warning("DeepSeek [%s]: hit max_tokens — the reasoning used up the output "
                            "budget before the answer was written", task)
            u = getattr(res, "usage", None)
            if u is not None:
                details = getattr(u, "completion_tokens_details", None)
                log.info(
                    "DeepSeek usage [%s, %s]: prompt=%s completion=%s (reasoning=%s)",
                    task, self.model_for(task),
                    getattr(u, "prompt_tokens", "?"), getattr(u, "completion_tokens", "?"),
                    getattr(details, "reasoning_tokens", "?") if details else "?",
                )
        except o.NotFoundError:
            log.warning("DeepSeek: model not found — check DEEPSEEK_MODEL")
            return None
        except o.RateLimitError:
            log.warning("DeepSeek: rate limited, try again later")
            return None
        except o.APIStatusError as e:
            log.warning("DeepSeek: HTTP %s", e.status_code)
            return None
        except o.APIConnectionError:
            log.warning("DeepSeek: could not reach the API")
            return None

        parsed = parse_reply(raw, schema)
        if parsed is None:
            log.warning("DeepSeek: no JSON object in the reply matched %s: %.300r",
                        schema.__name__, raw)
        return parsed


def build_provider(cfg: LLMConfig) -> _Provider | None:
    try:
        return AnthropicProvider(cfg) if cfg.provider == "anthropic" else DeepSeekProvider(cfg)
    except ImportError as e:
        log.warning("LLM provider %r unavailable: %s", cfg.provider, e)
        return None


_cached: _Provider | None = None


def get_provider() -> _Provider | None:
    """The server's own provider (memoised), or None if it has no key. Providers built
    from a user's key are never stored here: they live for one request."""
    global _cached
    if _cached is None:
        cfg = server_config()
        _cached = build_provider(cfg) if cfg else None
    return _cached


def is_enabled() -> bool:
    return get_provider() is not None


def provider_name() -> str:
    p = get_provider()
    return p.name if p else "none"


def model_name(task: str = "default", provider: _Provider | None = None) -> str:
    """Which model a task runs on — stored with results so a verdict says who judged it."""
    p = provider or get_provider()
    return p.model_for(task) if p else ""


# ---------------------------------------------------------------- public API
def generate_followups(
    title: str, number: int, difficulty: str, chapter: str, n: int = 3,
    provider: _Provider | None = None,
) -> list[FollowUpItem]:
    """Generate interviewer follow-ups for one problem. Results are cached in the DB,
    so each problem costs exactly one API call for its lifetime."""
    provider = provider or get_provider()
    if provider is None:
        return []

    prompt = f"""You are a senior software engineer interviewing a new-grad candidate.

The candidate has just finished this problem:
  LeetCode {number}. {title} ({difficulty}, category: {chapter})

Give {n} follow-up questions you would ask after they finish coding. Requirements:
- Questions a real interviewer asks, not textbook recitation
- Cover different angles: complexity optimisation, edge cases and failure modes,
  changing requirements (huge input, streaming data, concurrency), trade-offs against
  alternative approaches
- Order them from easier to harder
- Pair each question with the key points a strong answer covers, so the candidate can
  self-assess afterwards"""

    result = provider.complete(prompt, FollowUpBundle)
    return result.followups if result else []


def analyze_complexity(
    title: str,
    number: int,
    code: str,
    stated_time: str,
    stated_space: str,
    reference: tuple[list[str], list[str]] | None = None,
    provider: _Provider | None = None,
) -> ComplexityVerdict | None:
    """Judge the candidate's stated complexity against the code they actually wrote.

    The lookup table in complexity.py compares against the textbook solution, so an honest
    O(n^2) analysis of a brute-force answer is marked wrong. This asks the model about the
    code itself, and separately whether it is optimal. The table's answer is passed along
    as a hint, not as the answer key.
    """
    provider = provider or get_provider()
    if provider is None or not code.strip():
        return None

    ref = ""
    if reference:
        ref = (f"\nFor reference, the standard solution runs in {reference[0][0]} time and "
               f"{reference[1][0]} space. The candidate's code may use a different approach — "
               f"judge the code in front of you, not the standard solution.\n")

    prompt = f"""You are grading a new-grad candidate's complexity analysis in a coding interview.

Problem: LeetCode {number}. {title}

Their code:
```python
{code}
```

They stated: time {stated_time or "(blank)"}, space {stated_space or "(blank)"}.
{ref}
Rules:
- Analyse the code AS WRITTEN, including any inefficiency it has.
- Space means auxiliary space (recursion stack, hash maps, queues), excluding the returned
  output — but if the candidate's answer is only right when the output is counted, and
  that is a reasonable reading, accept it.
- Accept equivalent notation: O(n) for O(V) when n is the node count, O(m*n) for O(n*m),
  a stated bound that differs only by a constant.
- Do not accept a looser or tighter bound: O(n) is wrong for O(n log n), and O(n^2) is
  wrong for O(n) unless the code really is quadratic.
- Use the bounds interviewers use; do not re-derive amortised analyses. Union-Find with
  path compression counts as near-constant per operation, O(α(n)) ≈ O(1), whether or not
  it also unions by rank — do not dwell on the O(log n) path-compression-only bound. Hash
  map operations are O(1) average; comparison sorting is O(n log n).
- Keep your reasoning short: this is a quick judgement, not a proof.
- Big-O fields hold notation only, such as O(n log n) — never words or alternatives.
- why_wrong: only when an answer is wrong. Say what they missed, naming the variables
  (n = ..., V = ..., E = ...). Leave it empty when both answers are right.
- time_optimal / space_optimal: judge each separately; equivalent notation is equal.
- optimal_how and optimized_code: only when time OR space is not optimal.
- optimized_code: rewrite THEIR code minimally to reach the optimum, so a diff against
  their code shows only the optimisation. Copy every line that does not need to change
  exactly as written — same formatting, one-line ifs, blank lines, comments, spacing. Do
  not add imports (the judge provides them), type hints, docstrings or comments.
- Never use placeholders such as "..." — write the actual content or leave it empty."""

    # One retry when the reply parses but is incomplete (flash on the relay once returned
    # "..." for both the explanation and the rewrite).
    verdict = None
    for attempt in range(2):
        verdict = provider.complete(prompt, ComplexityVerdict, task="complexity")
        if verdict is None:
            return None
        problems = verdict_problems(verdict)
        if not problems:
            break
        log.warning("Incomplete complexity verdict (try %d): %s", attempt + 1, "; ".join(problems))
    return tidy_verdict(verdict)


def optimized_patch(user_code: str, optimized: str) -> tuple[str, list[str]]:
    """Validate the model's optimised rewrite and diff it against the candidate's code.

    Returns ("", []) when there is nothing worth showing: no rewrite, a rewrite identical
    to the original, or one that is not valid Python — a broken "improvement" is worse
    than none, and the model's code is otherwise shown unchecked.
    """
    code = optimized.strip()
    fenced = re.match(r"^```(?:python)?\s*\n(.*?)\n?```$", code, re.DOTALL)
    if fenced:
        code = fenced.group(1).strip()
    if not code:
        return "", []
    # "..." is valid Python (an Ellipsis expression) and once came back as the whole
    # "rewrite" — so require an actual function, not just something that parses.
    if "def " not in code or len(code.splitlines()) < 3:
        log.warning("optimized_code is not a real solution (%r) — not shown", code[:40])
        return "", []
    try:
        ast.parse(code)
    except SyntaxError as e:
        log.warning("optimized_code is not valid Python (%s) — not shown", e.msg)
        return "", []

    before = [line.rstrip() for line in user_code.strip().splitlines()]
    after = [line.rstrip() for line in code.splitlines()]
    if before == after:
        return "", []
    diff = list(difflib.unified_diff(
        before, after, fromfile="your code", tofile="optimized", lineterm="", n=2,
    ))
    return code, diff


def interview_followups(
    title: str, number: int, difficulty: str, code: str,
    stated_time: str = "", stated_space: str = "", n: int = 3,
    provider: _Provider | None = None,
) -> list[FollowUpItem]:
    """Follow-up questions about the code the candidate just wrote.

    generate_followups() asks about the problem in general and is cached per problem; these
    are specific to one submission, the way a real interviewer reacts to what is on the
    screen: the recursion depth of this DFS, the extra array this DP allocates.
    """
    provider = provider or get_provider()
    if provider is None or not code.strip():
        return []

    prompt = f"""You are a senior engineer running a coding interview for a new-grad role.

The candidate just solved LeetCode {number}. {title} ({difficulty}) with this code:

```python
{code}
```

They stated the complexity as: time {stated_time or "(not stated)"}, space {stated_space or "(not stated)"}.

Ask the {n} follow-up questions you would ask about THIS code in a real interview. Rules:
- Ground each question in the code on screen — refer to its actual choices (the recursion,
  the extra array, the data structure picked, how it handles a particular input).
- If the stated complexity is wrong, or the code is not optimal, one question should
  probe that without giving the answer away.
- Mix angles: optimisation or trade-offs, an edge case or failure mode this code might
  hit, and a requirement change (scale, streaming, concurrency, a variant of the problem).
- Order from easier to harder. One sentence per question, no hints inside the question.
- If a question uses an input the problem's constraints rule out, say so in the question,
  and write key points that accept any well-reasoned behaviour rather than one answer.
- For each, give the key points a strong answer covers (two or three sentences). These
  are hidden from the candidate until they answer."""

    result = provider.complete(prompt, FollowUpBundle, task="interview")
    return result.followups[:n] if result else []


def grade_answer(
    title: str, number: int, code: str, question: str, key_points: str, answer: str,
    provider: _Provider | None = None,
) -> AnswerGrade | None:
    """Grade a candidate's written answer to one follow-up question."""
    provider = provider or get_provider()
    if provider is None or not answer.strip():
        return None

    prompt = f"""You are the interviewer. Grade the candidate's answer to your follow-up question.

Problem: LeetCode {number}. {title}
Their code:
```python
{code}
```

Your question: {question}
Key points you were looking for: {key_points}

Their answer (verbatim, between the tags):
<answer>
{answer}
</answer>

Grading:
- 4 strong: correct and complete, would move the interview forward with confidence
- 3 good: correct with a minor gap
- 2 partial: right direction but a significant gap or imprecision
- 1 weak: incorrect, or does not address the question
Judge the substance, not the wording or language — a terse correct answer is still
correct. Credit valid points that are not in your key points. Be specific about what is
missing; do not invent gaps to fill the list.

Your key points were written in advance and may be incomplete or wrong. If the answer
contradicts them with a sound argument, re-check the problem statement and constraints
yourself instead of deducting for the disagreement. Where the question is genuinely
ambiguous (for example an input the problem's constraints rule out), accept any
well-reasoned position and say that it is ambiguous."""

    return provider.complete(prompt, AnswerGrade, task="interview")
