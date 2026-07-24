import pytest


@pytest.fixture
def rag(monkeypatch, tmp_path):
    # Point Chroma at a temp dir before importing the module-level singleton.
    import importlib

    monkeypatch.setenv("OPIK_EXAMPLES_MODEL", "anthropic/claude-sonnet-4-6")
    import optimization_guide.config as config

    importlib.reload(config)
    monkeypatch.setattr(config, "CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setattr(config, "COLLECTION", "test_docs")
    import optimization_guide.rag_app as rag_app

    importlib.reload(rag_app)
    # reset cached singleton
    rag_app._collection = None
    return rag_app


def test_ingest_and_retrieve(rag):
    docs = [
        {"id": "a", "title": "Timeouts", "text": "The default job timeout is 30 seconds."},
        {"id": "b", "title": "Regions", "text": "The default region is us-east."},
    ]
    count = rag.ingest(docs)
    assert count == 2
    hits = rag.retrieve("what is the default timeout", n_results=1)
    assert len(hits) == 1
    assert "30 seconds" in hits[0]


def test_answer_uses_context_and_prompt(rag, monkeypatch):
    rag.ingest([{"id": "a", "title": "Timeouts", "text": "The default job timeout is 30 seconds."}])
    captured = {}

    def fake_completion(model, messages, **kwargs):
        captured["model"] = model
        captured["messages"] = messages

        class R:
            choices = [type("C", (), {"message": type("M", (), {"content": "It is 30 seconds."})()})()]
        return R()

    monkeypatch.setattr(rag.litellm, "completion", fake_completion)
    out = rag.answer(
        "what is the default timeout",
        system_prompt="You are helpful.",
        model="anthropic/claude-sonnet-4-6",
    )
    assert out == "It is 30 seconds."
    # system prompt propagated, context injected
    assert captured["messages"][0]["role"] == "system"
    assert "You are helpful." in captured["messages"][0]["content"]
    assert any("30 seconds" in m["content"] for m in captured["messages"])


def test_should_retrieve_parses_yes(rag, monkeypatch):
    def fake_completion(model, messages, **kwargs):
        class R:
            choices = [type("C", (), {"message": type("M", (), {"content": "YES"})()})()]
        return R()

    monkeypatch.setattr(rag.litellm, "completion", fake_completion)
    assert rag.should_retrieve("how do I configure retries?") is True
