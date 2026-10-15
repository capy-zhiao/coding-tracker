"""AI complexity analysis: the DeepSeek request shape, reply parsing, and the endpoint.

No network: the provider's HTTP client and get_provider() are replaced with fakes.
"""
from types import SimpleNamespace

import pytest

from app import llm
from app.config import settings
from app.llm import ComplexityVerdict, DeepSeekProvider, extract_json, server_config


# ---------------------------------------------------------------- reply parsing

@pytest.mark.parametrize("raw", [
    '{"x": 1}',
    '```json\n{"x": 1}\n```',
    '```\n{"x": 1}\n```',
    'Sure, here it is: {"x": 1} — let me know.',
])
def test_extract_json_tolerates_fences_and_chatter(raw):
    assert extract_json(raw) == '{"x": 1}'


# ---------------------------------------------------------------- DeepSeek request

class FakeCompletions:
    def __init__(self, content):
        self.content, self.calls = content, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=SimpleNamespace(prompt_tokens=700, completion_tokens=1800,
                                  completion_tokens_details=SimpleNamespace(reasoning_tokens=1650)),
        )


def make_provider(monkeypatch, content):
    """The server's own provider, built from settings the way the app builds it."""
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    provider = DeepSeekProvider(server_config())
    fake = FakeCompletions(content)
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return provider, fake


VERDICT_JSON = ('{"actual_time": "O(V + E)", "actual_space": "O(V)", "time_correct": false, '
                '"space_correct": true, "why_wrong": "O(n) ignores the E neighbour visits.", '
                '"optimal_time": "O(V + E)", "optimal_space": "O(V)", '
                '"time_optimal": true, "space_optimal": true}')


def test_thinking_mode_is_requested(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_thinking", True)
    monkeypatch.setattr(settings, "deepseek_reasoning_effort", "high")
    provider, fake = make_provider(monkeypatch, VERDICT_JSON)
    provider.complete("p", ComplexityVerdict)

    sent = fake.calls[0]
    assert sent["extra_body"]["thinking"] == {"type": "enabled"}
    assert sent["extra_body"]["reasoning_effort"] == "high"
    assert sent["max_tokens"] >= 16000, "reasoning tokens count towards max_tokens"


def test_thinking_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_thinking", False)
    provider, fake = make_provider(monkeypatch, VERDICT_JSON)
    provider.complete("p", ComplexityVerdict)
    assert fake.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}


def test_fenced_reply_still_parses(monkeypatch):
    provider, _ = make_provider(monkeypatch, f"```json\n{VERDICT_JSON}\n```")
    v = provider.complete("p", ComplexityVerdict)
    assert v is not None and v.actual_time == "O(V + E)"


def test_malformed_reply_returns_none(monkeypatch):
    provider, _ = make_provider(monkeypatch, "I think it's linear?")
    assert provider.complete("p", ComplexityVerdict) is None


# ---------------------------------------------------------------- endpoint

class StubProvider:
    name = "stub"

    def __init__(self, verdict):
        self.verdict, self.prompts = verdict, []

    def model_for(self, task="default"):
        return f"stub-{task}"

    def complete(self, prompt, schema, task="default"):
        self.tasks = getattr(self, "tasks", []) + [task]
        self.prompts.append(prompt)
        return self.verdict


def verdict(**over):
    base = dict(actual_time="O(m * n)", actual_space="O(m * n)", time_correct=True,
                space_correct=True, optimal_time="O(m * n)", optimal_space="O(m * n)",
                time_optimal=True, space_optimal=True)
    return ComplexityVerdict(**{**base, **over})


@pytest.fixture
def stub(monkeypatch):
    holder = {}

    def install(v):
        holder["p"] = StubProvider(v)
        monkeypatch.setattr(llm, "get_provider", lambda: holder["p"])
        return holder["p"]
    return install


def submit(client, number, code="def f(): pass", t="O(n)", s="O(n)"):
    r = client.post(f"/review/{number}/attempt", json={
        "grade": "good", "code": code, "time_complexity": t, "space_complexity": s})
    return r.json()["attempt"]["id"]


def test_ai_off_is_503(client, sample_problems):
    aid = submit(client, 200)
    assert client.post(f"/review/attempts/{aid}/complexity-ai").status_code == 503


def test_verdict_is_stored_and_decides_complexity_ok(client, sample_problems, stub):
    stub(verdict(time_correct=True, space_correct=False, actual_space="O(m * n)",
                 why_wrong="The visited set holds every cell, so space is O(m * n)."))
    aid = submit(client, 200, t="O(m*n)", s="O(1)")

    body = client.post(f"/review/attempts/{aid}/complexity-ai").json()
    assert body["complexity_ai"]["actual_space"] == "O(m * n)"
    assert body["complexity_ok"] is False

    history = client.get("/review/200/attempts").json()
    assert history[0]["complexity_ai"]["time_correct"] is True


def test_ai_overrides_the_table_for_an_honest_brute_force(client, sample_problems, stub):
    """The point of the feature: O(n^2) is right for a quadratic solution even though the
    textbook answer is O(n) — the table marks it wrong, the AI marks it right."""
    stub(verdict(actual_time="O(n^2)", time_correct=True, time_optimal=False,
                 optimal_time="O(n)", actual_space="O(1)", space_correct=True,
                 optimal_how="One pass with a hash map of complements."))
    aid = submit(client, 1, t="O(n^2)", s="O(1)")        # Two Sum, nested loops
    assert client.get("/review/1/attempts").json()[0]["complexity_ok"] is False  # table

    body = client.post(f"/review/attempts/{aid}/complexity-ai").json()
    assert body["complexity_ok"] is True
    assert body["complexity_ai"]["time_optimal"] is False

    stats = client.get("/stats/complexity").json()
    assert stats["graded"] == 1 and stats["both_correct"] == 1


def test_prompt_carries_the_code_the_answer_and_the_reference(client, sample_problems, stub):
    p = stub(verdict())
    aid = submit(client, 200, code="def numIslands(grid): ...", t="O(m*n)", s="O(m*n)")
    client.post(f"/review/attempts/{aid}/complexity-ai")
    prompt = p.prompts[0]
    assert "def numIslands(grid)" in prompt
    assert "time O(m*n), space O(m*n)" in prompt
    assert "standard solution runs in O(m * n)" in prompt


def test_attempt_without_code_is_400(client, sample_problems, stub):
    stub(verdict())
    aid = submit(client, 200, code="   ")
    assert client.post(f"/review/attempts/{aid}/complexity-ai").status_code == 400


def test_unknown_attempt_is_404(client, stub):
    stub(verdict())
    assert client.post("/review/attempts/99999/complexity-ai").status_code == 404


def test_failed_ai_call_is_502_and_changes_nothing(client, sample_problems, stub):
    stub(None)
    aid = submit(client, 200, t="O(m*n)", s="O(m*n)")
    assert client.post(f"/review/attempts/{aid}/complexity-ai").status_code == 502
    a = client.get("/review/200/attempts").json()[0]
    assert a["complexity_ai"] is None and a["complexity_ok"] is True


# ---------------------------------------------------------------- relay quirks

from app.llm import AnswerGrade, FollowUpBundle, describe_fields, json_candidates, parse_reply

ECHOED = '''{"properties": {"score": {"type": "integer"}}, "required": ["score"], "type": "object"}
```json
{"score": 3, "feedback": "Good.", "missing": [], "model_answer": "Keep two {rolling} values."}
```'''


def test_reply_that_echoes_the_schema_first_still_parses():
    """Seen on a relay: the schema is repeated verbatim, then the real answer is fenced."""
    g = parse_reply(ECHOED, AnswerGrade)
    assert g is not None and g.score == 3


def test_braces_inside_strings_do_not_split_objects():
    raw = '{"score": 2, "feedback": "use {x}", "missing": ["a } b"], "model_answer": "m"}'
    assert json_candidates(raw) == [raw]
    assert parse_reply(raw, AnswerGrade).missing == ["a } b"]


def test_no_valid_object_returns_none():
    assert parse_reply('{"nope": 1} and {"also": 2}', AnswerGrade) is None


def test_field_list_is_sent_instead_of_raw_schema():
    listing = describe_fields(AnswerGrade)
    assert '"score" (integer (1..4))' in listing
    assert '"missing" (array of string)' in listing
    assert '"properties"' not in listing


def test_nested_item_fields_are_described(monkeypatch):
    provider, fake = make_provider(monkeypatch, '{"followups": []}')
    provider.complete("P", FollowUpBundle)
    content = fake.calls[0]["messages"][0]["content"]
    assert 'Each element of "followups"' in content and '"hint" (string)' in content



# ---------------------------------------------------------------- per-task models

def test_complexity_can_run_on_a_cheaper_model(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_model", "deepseek-v4-pro")
    monkeypatch.setattr(settings, "deepseek_complexity_model", "deepseek-v4-flash")
    provider, fake = make_provider(monkeypatch, VERDICT_JSON)
    provider.complete("p", ComplexityVerdict, task="complexity")
    provider.complete("p", ComplexityVerdict, task="interview")
    assert [c["model"] for c in fake.calls] == ["deepseek-v4-flash", "deepseek-v4-pro"]


def test_empty_override_falls_back_to_the_default_model(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_model", "deepseek-v4-pro")
    monkeypatch.setattr(settings, "deepseek_complexity_model", "")
    provider, _ = make_provider(monkeypatch, VERDICT_JSON)
    assert provider.model_for("complexity") == "deepseek-v4-pro"


def test_stored_verdict_records_the_model_that_judged_it(client, sample_problems, stub):
    p = stub(verdict())
    aid = submit(client, 200, t="O(m*n)", s="O(m*n)")
    body = client.post(f"/review/attempts/{aid}/complexity-ai").json()
    assert body["complexity_ai"]["model"] == "stub-complexity"
    assert p.tasks == ["complexity"]


# ---------------------------------------------------------------- optimised rewrite

from app.llm import optimized_patch

DP_ARRAY = """class Solution:
    def rob(self, nums):
        dp = [0] * len(nums)
        dp[0] = nums[0]
        for i in range(1, len(nums)):
            dp[i] = max(nums[i] + (dp[i - 2] if i > 1 else 0), dp[i - 1])
        return dp[-1]"""
ROLLING = """class Solution:
    def rob(self, nums):
        prev2, prev1 = 0, 0
        for i in range(len(nums)):
            prev2, prev1 = prev1, max(nums[i] + prev2, prev1)
        return prev1"""


def test_rewrite_is_diffed_against_the_submitted_code():
    code, diff = optimized_patch(DP_ARRAY, ROLLING)
    assert code == ROLLING
    assert diff[0] == "--- your code" and diff[1] == "+++ optimized"
    assert any(line.startswith("-        dp = [0]") for line in diff)
    assert any(line.startswith("+        prev2, prev1 = 0, 0") for line in diff)


def test_markdown_fence_around_the_rewrite_is_stripped():
    code, _ = optimized_patch(DP_ARRAY, f"```python\n{ROLLING}\n```")
    assert code == ROLLING


@pytest.mark.parametrize("rewrite", ["", "   ", "...", "pass", "def rob(:\n    pass", DP_ARRAY])
def test_nothing_shown_for_empty_broken_or_unchanged_rewrites(rewrite):
    assert optimized_patch(DP_ARRAY, rewrite) == ("", [])


def test_endpoint_stores_the_validated_rewrite_and_diff(client, sample_problems, stub):
    stub(verdict(actual_space="O(n)", optimal_space="O(1)", space_optimal=False,
                 optimal_how="Keep only the last two values.", optimized_code=ROLLING))
    aid = submit(client, 200, code=DP_ARRAY, t="O(n)", s="O(n)")
    ai = client.post(f"/review/attempts/{aid}/complexity-ai").json()["complexity_ai"]
    assert ai["optimized_code"] == ROLLING
    assert ai["optimized_diff"][0] == "--- your code"


def test_endpoint_drops_a_rewrite_that_does_not_parse(client, sample_problems, stub):
    stub(verdict(space_optimal=False, optimal_how="Two rolling variables instead.",
                 optimized_code="def rob(:"))
    aid = submit(client, 200, code=DP_ARRAY)
    ai = client.post(f"/review/attempts/{aid}/complexity-ai").json()["complexity_ai"]
    assert ai["optimized_code"] == "" and ai["optimized_diff"] == []



# ---------------------------------------------------------------- verdict hygiene

from app.llm import first_big_o, tidy_verdict, verdict_problems


@pytest.mark.parametrize("raw,want", [
    ("O(V+E) (or O(V) with early edge count check)", "O(V+E)"),
    ("O(n log n)", "O(n log n)"),
    ("about O(log (m + n)) overall", "O(log (m + n))"),
    ("linear", ""),
])
def test_first_big_o_strips_prose(raw, want):
    assert first_big_o(raw) == want


def test_a_wrong_answer_needs_a_reason():
    v = verdict(time_correct=False, why_wrong="...")
    assert "why_wrong missing for a wrong answer" in verdict_problems(v)


def test_a_non_optimal_solution_needs_the_technique():
    v = verdict(space_optimal=False, optimal_how="")
    assert any("optimal_how" in p for p in verdict_problems(v))


def test_a_complete_verdict_has_no_problems():
    assert verdict_problems(verdict()) == []


def test_tidy_blanks_placeholders_and_trims_notation():
    v = tidy_verdict(verdict(optimal_time="O(V+E) (or O(V))", why_wrong="..."))
    assert v.optimal_time == "O(V+E)" and v.why_wrong == ""


class SequenceProvider(StubProvider):
    """Returns the given verdicts in order, one per call."""
    def __init__(self, replies):
        super().__init__(None)
        self.replies = list(replies)

    def complete(self, prompt, schema, task="default"):
        self.prompts.append(prompt)
        return self.replies.pop(0)


def test_incomplete_verdict_is_retried_once(monkeypatch):
    lazy = verdict(time_correct=False, why_wrong="...")
    good = verdict(time_correct=False, why_wrong="The sort makes it O(n log n), not O(n).")
    p = SequenceProvider([lazy, good])
    monkeypatch.setattr(llm, "get_provider", lambda: p)
    v = llm.analyze_complexity("X", 1, "def f(): pass", "O(n)", "O(1)")
    assert len(p.prompts) == 2 and v.why_wrong.startswith("The sort")


def test_still_incomplete_after_retry_is_tidied_not_shown_raw(monkeypatch):
    lazy = verdict(time_correct=False, why_wrong="...")
    p = SequenceProvider([lazy, verdict(time_correct=False, why_wrong="...")])
    monkeypatch.setattr(llm, "get_provider", lambda: p)
    v = llm.analyze_complexity("X", 1, "def f(): pass", "O(n)", "O(1)")
    assert len(p.prompts) == 2 and v.why_wrong == ""


def test_no_rewrite_shown_when_already_optimal(client, sample_problems, stub):
    stub(verdict(optimized_code=ROLLING))          # optimal in both, yet code returned
    aid = submit(client, 200, code=DP_ARRAY)
    ai = client.post(f"/review/attempts/{aid}/complexity-ai").json()["complexity_ai"]
    assert ai["optimized_code"] == "" and ai["optimized_diff"] == []



def test_complexity_check_uses_its_own_reasoning_effort(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_thinking", True)
    monkeypatch.setattr(settings, "deepseek_reasoning_effort", "high")
    monkeypatch.setattr(settings, "deepseek_complexity_effort", "low")
    provider, fake = make_provider(monkeypatch, VERDICT_JSON)
    provider.complete("p", ComplexityVerdict, task="complexity")
    provider.complete("p", ComplexityVerdict, task="interview")
    assert [c["extra_body"]["reasoning_effort"] for c in fake.calls] == ["low", "high"]
