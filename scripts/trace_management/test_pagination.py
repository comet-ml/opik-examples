#!/usr/bin/env python3
"""
Offline tests for the delete loop's pagination. No credentials, no network, no writes.

These exist because the bug they cover — a delete loop that never terminated above
one page — was invisible to the live end-to-end script in test_manage_traces.py,
which only ever seeds ~70 traces. Anything that touches how pages are walked
should be covered here, where a regression costs milliseconds to catch.

Run:  uv run python test_pagination.py
"""

import sys
from datetime import UTC, datetime

import manage_traces as mt


class FakeStore:
    """A project holding `n` traces, served newest-id-first, honouring deletes."""

    def __init__(self, n: int, page_size: int, deletes_work: bool = True):
        # Ids must sort the way real UUIDv7 ids do, so ordering is reproducible.
        self.ids = [f"{i:08x}-0000-7000-8000-000000000000" for i in range(n, 0, -1)]
        self.page_size = page_size
        self.deletes_work = deletes_work
        self.search_calls = 0
        self.deleted: list[str] = []

    def search_page(self, client, project_name, tf, limit, cursor=None):
        self.search_calls += 1
        if self.search_calls > 500:  # Backstop so a regression fails instead of hanging.
            raise AssertionError(f"no termination after {self.search_calls} searches")
        page = self.ids[: min(limit, self.page_size)]
        return [_FakeTrace(i) for i in page]

    def delete(self, ids, project_id=None):
        self.deleted.extend(ids)
        if self.deletes_work:
            remaining = set(self.ids) - set(ids)
            self.ids = [i for i in self.ids if i in remaining]


class _FakeTrace:
    def __init__(self, id_):
        self.id = id_
        self.start_time = datetime.now(tz=UTC)


class _FakeClient:
    def __init__(self, store):
        self.rest_client = type(
            "RC", (), {"traces": type("T", (), {"delete_traces": staticmethod(store.delete)})()}
        )()


def _run(n, page_size=1000, deletes_work=True):
    store = FakeStore(n, page_size, deletes_work)
    mt._search_page = store.search_page
    mt._FAILED = False
    deleted = mt.delete_matching(
        _FakeClient(store), "proj", "proj-id", mt.TraceFilter(before=datetime.now(tz=UTC))
    )
    return store, deleted


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{'  — ' + detail if detail and not cond else ''}")
    return cond


def check_time_field() -> bool:
    """Date bounds must land on exactly one clock — never both.

    to_time/from_time bound the trace id; a start_time predicate bounds the trace's own
    timestamp. They are AND-combined server-side, so emitting both would re-exclude the
    backfilled traces the start_time default exists to catch.
    """
    ok = True
    before = datetime(2025, 1, 17, tzinfo=UTC)
    after = datetime(2024, 6, 1, tzinfo=UTC)

    st = mt.TraceFilter(before=before, after=after, time_field="start_time")
    fields = [f.field for f in st.to_sdk_filters()]
    ok &= check("start_time: emits start_time predicates", fields.count("start_time") == 2, str(fields))
    ok &= check("start_time: sends no to_time/from_time", st.to_api_kwargs() == {}, str(st.to_api_kwargs()))

    ing = mt.TraceFilter(before=before, after=after, time_field="ingestion")
    kwargs = ing.to_api_kwargs()
    ok &= check(
        "ingestion: sends to_time + from_time", set(kwargs) == {"to_time", "from_time"}, str(set(kwargs))
    )
    ok &= check(
        "ingestion: emits no start_time predicate",
        "start_time" not in [f.field for f in ing.to_sdk_filters()],
    )

    # Tags must survive on either clock, and stay AND-combined.
    tagged = mt.TraceFilter(before=before, tags=["a", "b"], exclude_tags=["c"], time_field="ingestion")
    ops = [(f.field, f.operator) for f in tagged.to_sdk_filters()]
    ok &= check(
        "tags preserved under ingestion clock",
        ops == [("tags", "contains"), ("tags", "contains"), ("tags", "not_contains")],
        str(ops),
    )

    ok &= check(
        "sorting follows the active clock",
        "start_time" in st.sorting("DESC") and '"id"' in ing.sorting("DESC"),
    )
    return ok


def main() -> int:
    ok = True
    original = mt._search_page
    try:
        # The regression case. The previous implementation re-requested page 1
        # forever here, because it only stopped on a short page.
        print("\n2,500 traces / 1,000 per page (the case that used to hang):")
        store, deleted = _run(2500)
        ok &= check("terminates", True)
        ok &= check(
            "deletes every trace exactly once",
            deleted == 2500 and len(set(store.deleted)) == 2500,
            f"deleted={deleted}, unique={len(set(store.deleted))}",
        )
        ok &= check("store is empty afterwards", store.ids == [], f"{len(store.ids)} left")

        print("\nBoundary sizes:")
        for n in (0, 1, 999, 1000, 1001, 4001):
            store, deleted = _run(n)
            ok &= check(f"n={n}", deleted == n and store.ids == [], f"deleted={deleted}")

        print("\nSmaller-than-page batching (200 per delete call):")
        store, deleted = _run(450)
        ok &= check("450 traces deleted", deleted == 450)
        ok &= check("no id deleted twice", len(set(store.deleted)) == 450)

        print("\nDate-bound clock selection:")
        ok &= check_time_field()

        print("\nProgress guard (deletes silently not taking effect):")
        store, deleted = _run(2500, deletes_work=False)
        ok &= check("bails instead of looping forever", True)
        ok &= check("marks the run as failed", mt._FAILED, "_FAILED was not set")
        ok &= check("stopped after one round", store.search_calls <= 3, f"{store.search_calls} searches")
    except AssertionError as e:
        print(f"  FAIL  {e}")
        ok = False
    finally:
        mt._search_page = original

    print("\n" + ("All pagination tests passed." if ok else "FAILURES — see above."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
