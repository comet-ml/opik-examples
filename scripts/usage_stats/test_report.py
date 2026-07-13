import datetime
import inspect

import pandas as pd

import report


def _frames():
    daily = pd.DataFrame(
        [
            {
                "workspace": "w",
                "project_id": "1",
                "project": "alpha",
                "metric": "TRACE_COUNT",
                "series": "",
                "date": pd.Timestamp("2026-07-01"),
                "value": 5.0,
            },
            {
                "workspace": "w",
                "project_id": "1",
                "project": "alpha",
                "metric": "SPAN_COUNT",
                "series": "",
                "date": pd.Timestamp("2026-07-01"),
                "value": 12.0,
            },
            {
                "workspace": "w",
                "project_id": "1",
                "project": "alpha",
                "metric": "THREAD_COUNT",
                "series": "",
                "date": pd.Timestamp("2026-07-02"),
                "value": 2.0,
            },
            {
                "workspace": "w",
                "project_id": "1",
                "project": "alpha",
                "metric": "TOKEN_USAGE",
                "series": "gpt-4o",
                "date": pd.Timestamp("2026-07-01"),
                "value": 900.0,
            },
            {
                "workspace": "w",
                "project_id": "1",
                "project": "alpha",
                "metric": "COST",
                "series": "",
                "date": pd.Timestamp("2026-07-01"),
                "value": 0.42,
            },
        ]
    )
    summary = pd.DataFrame(
        [
            {"project": "alpha", "metric": "TRACE_COUNT", "value": 5.0},
            {"project": "alpha", "metric": "THREAD_COUNT", "value": 2.0},
            {"project": "alpha", "metric": "TOKENS_TOTAL", "value": 900.0},
            {"project": "alpha", "metric": "TOTAL_COST", "value": 0.42},
            {"project": "alpha", "metric": "GUARDRAILS_FAILED_COUNT", "value": 0.0},
        ]
    )
    return daily, summary


def _render(**over):
    daily, summary = _frames()
    kwargs = dict(
        workspace="myws",
        window_start=datetime.date(2026, 7, 1),
        window_end=datetime.date(2026, 7, 31),
        generated=datetime.datetime(2026, 7, 31, 12, 0),
        df_daily=daily,
        df_summary=summary,
    )
    kwargs.update(over)
    return report.render_html(**kwargs)


def test_line_chart_has_polyline_axes_and_crosshair():
    svg = report._line_chart_svg("c1", ["Jul 01", "Jul 02", "Jul 03"], [1.0, 3.0, 2.0])
    assert svg.startswith("<svg")
    assert "polyline" in svg
    assert 'class="ylab"' in svg and 'class="xlab"' in svg   # value + date axis labels
    assert "Jul 01" in svg                                   # x date label rendered
    assert 'class="cross"' in svg and 'class="dot"' in svg   # crosshair layer present


def test_bar_chart_has_one_rect_per_value_plus_axes():
    svg = report._bar_chart_svg("c2", ["Jul 01", "Jul 02"], [1.0, 2.0])
    assert svg.count('class="bar"') == 2                     # one bar per value (gridlines are <line>)
    assert 'class="ylab"' in svg and 'class="xlab"' in svg
    assert 'class="cross"' in svg                            # crosshair layer present


def test_empty_series_render_safe():
    assert report._line_chart_svg("c", [], []).startswith("<svg")
    assert report._bar_chart_svg("c", [], []).startswith("<svg")


def test_render_html_has_all_sections():
    out = _render()
    assert "myws" in out                       # header workspace
    assert "2026-07-31" in out                  # generated date
    for label in ("Traces", "Spans", "Threads"):
        assert label in out                     # count-metric charts
    assert "alpha" in out                       # snapshot table row
    assert "Token usage" in out                 # magnitude table
    assert "Estimated cost" in out              # magnitude table
    assert "cometx" in out                      # growth footer link
    assert "growth-report" in out               # exact cometx anchor
    assert "prefers-color-scheme" in out        # light/dark styling
    assert 'id="chartdata"' in out              # embedded data for crosshair JS
    assert "getScreenCTM" in out                # inline crosshair/tooltip layer


def test_renderer_takes_no_credential():
    for fn in (report.render_html, report.write_report):
        assert "api_key" not in inspect.signature(fn).parameters


def test_no_secret_sentinel_in_output():
    out = _render()
    assert "sk-LEAKED-KEY-DO-NOT-EMBED" not in out
    assert "OPIK_API_KEY" not in out


def test_write_report_writes_file(tmp_path):
    daily, summary = _frames()
    dest = tmp_path / "report.html"
    report.write_report(
        str(dest),
        workspace="myws",
        window_start=datetime.date(2026, 7, 1),
        window_end=datetime.date(2026, 7, 31),
        generated=datetime.datetime(2026, 7, 31, 12, 0),
        df_daily=daily,
        df_summary=summary,
    )
    text = dest.read_text(encoding="utf-8")
    assert text.lstrip().startswith("<!doctype html")
    assert "alpha" in text


def test_render_html_empty_frames_safe():
    empty_daily = pd.DataFrame(
        columns=["workspace", "project_id", "project", "metric", "series", "date", "value"]
    )
    empty_summary = pd.DataFrame(columns=["project", "metric", "value"])
    out = report.render_html(
        workspace="myws",
        window_start=datetime.date(2026, 7, 1),
        window_end=datetime.date(2026, 7, 31),
        generated=datetime.datetime(2026, 7, 31, 12, 0),
        df_daily=empty_daily,
        df_summary=empty_summary,
    )
    assert "No snapshot data." in out
    assert "No temporal data" in out
    assert "cometx" in out
