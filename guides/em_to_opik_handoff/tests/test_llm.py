from types import SimpleNamespace

import pytest

from roadwork_demo import llm
from roadwork_demo.llm import image_block, structured_json

SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string"}, "reason": {"type": "string"}},
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}


class FakeCompletion:
    """Stands in for the tracked litellm.completion: records the request, returns a canned answer."""

    def __init__(self):
        self.calls = []
        self.content = '{"verdict": "clear", "reason": "open"}'
        self.finish_reason = "stop"

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=self.finish_reason)])


@pytest.fixture
def fake(monkeypatch):
    fake = FakeCompletion()
    monkeypatch.setattr(llm, "completion", lambda: fake)
    return fake


def test_image_block_is_an_image_url_part():
    assert image_block("QUJD") == {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}}


def test_parses_json_answer(fake):
    parsed, raw = structured_json("m", "sys", [{"type": "text", "text": "x"}], SCHEMA, 100)
    assert parsed == {"verdict": "clear", "reason": "open"} and raw.startswith("{")


def test_request_shape(fake):
    structured_json("anthropic/x", "sys", [{"type": "text", "text": "x"}], SCHEMA, 100)
    kw = fake.calls[0]
    assert kw["model"] == "anthropic/x" and kw["max_tokens"] == 100
    assert kw["messages"][0] == {"role": "system", "content": "sys"}
    assert kw["messages"][1] == {"role": "user", "content": [{"type": "text", "text": "x"}]}
    assert kw["response_format"]["type"] == "json_schema"
    assert kw["response_format"]["json_schema"]["schema"] == SCHEMA


def test_non_json_text_returns_none_and_the_raw_text(fake):
    fake.content = "I think it is blocked"
    assert structured_json("m", "s", [], SCHEMA, 100) == (None, "I think it is blocked")


def test_json_that_is_not_an_object_returns_none(fake):
    fake.content = '["blocked"]'
    assert structured_json("m", "s", [], SCHEMA, 100) == (None, '["blocked"]')


def test_empty_or_refused_answer_returns_none(fake):
    fake.content = None
    fake.finish_reason = "content_filter"
    parsed, raw = structured_json("m", "s", [], SCHEMA, 100)
    assert parsed is None and "content_filter" in raw
