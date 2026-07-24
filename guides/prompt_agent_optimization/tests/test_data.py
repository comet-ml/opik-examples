from optimization_guide import data


def test_load_docs_shape():
    docs = data.load_docs()
    assert len(docs) >= 10
    assert all({"id", "title", "text"} <= set(d) for d in docs)


def test_load_exact_cases_grounded():
    docs = data.load_docs()
    corpus = " ".join(d["text"] for d in docs)
    cases = data.load_exact_cases()
    assert len(cases) >= 15
    for c in cases:
        assert c["expected_substring"] in corpus


def test_load_judge_cases_shape():
    cases = data.load_judge_cases()
    assert len(cases) >= 10
    assert all({"query", "reference"} <= set(c) for c in cases)


class _FakeDataset:
    def __init__(self, name):
        self.name = name
        self.items = []

    def insert(self, items):
        self.items.extend(items)


class _FakeClient:
    def __init__(self):
        self.created = {}

    def get_or_create_dataset(self, name):
        ds = self.created.setdefault(name, _FakeDataset(name))
        return ds


def test_build_dataset_inserts_cases():
    client = _FakeClient()
    cases = [{"query": "q1", "expected_substring": "a"}, {"query": "q2", "expected_substring": "b"}]
    ds = data.build_dataset(client, "exact-eval", cases)
    assert ds.name == "exact-eval"
    assert len(ds.items) == 2
    assert ds.items[0]["query"] == "q1"
