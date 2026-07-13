"""Self-contained HTML report for Opik usage stats — dependency-free inline SVG.

Consumes plain pandas DataFrames produced by run_usage_stats.py and writes a
single themed, offline-openable report.html. Charts are server-rendered inline
SVG (axes + marks) with a small inline-JS crosshair/tooltip layer on top —
progressive enhancement, so the charts still read with JavaScript disabled.
No external assets, no CDN, and no credential is ever embedded.
"""

from __future__ import annotations

import datetime
import html
import json
import math

import pandas as pd

COUNT_METRICS = [("TRACE_COUNT", "Traces"), ("SPAN_COUNT", "Spans"), ("THREAD_COUNT", "Threads")]
SNAPSHOT_COLUMNS = [
    ("TRACE_COUNT", "Traces"),
    ("THREAD_COUNT", "Threads"),
    ("TOKENS_TOTAL", "Tokens"),
    ("TOTAL_COST", "Est. cost"),
    ("GUARDRAILS_FAILED_COUNT", "Guardrail fails"),
]
MAGNITUDE_METRICS = [("TOKEN_USAGE", "Token usage", False), ("COST", "Estimated cost", True)]
COMETX_URL = "https://github.com/comet-ml/cometx/blob/main/README.md#growth-report"

# Chart geometry (viewBox units). Shared by the Python mark renderer and the
# inline JS crosshair so both map data → pixels identically.
_CW, _CH = 720, 210
_ML, _MR, _MT, _MB = 52, 16, 12, 40
_PL = _CW - _ML - _MR  # plot width
_PH = _CH - _MT - _MB  # plot height
_GEOM = {"ml": _ML, "mt": _MT, "pl": _PL, "ph": _PH, "w": _CW, "h": _CH}

_CSS = """
:root { --bg:#fff; --fg:#1a1a1a; --muted:#666; --card:#f6f7f9; --line:#e3e6ea;
        --accent:#4a86e8; --area:rgba(74,134,232,.15); }
@media (prefers-color-scheme: dark) {
  :root { --bg:#12141a; --fg:#e8eaed; --muted:#9aa0a6; --card:#1c1f27; --line:#2a2e38;
          --accent:#8ab4f8; --area:rgba(138,180,248,.15); } }
* { box-sizing:border-box; } body { margin:0; padding:2rem; background:var(--bg); color:var(--fg);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
h1 { font-size:1.4rem; margin:0 0 .25rem; } h2 { font-size:1.05rem; margin:2rem 0 .5rem; }
h3 { font-size:.85rem; color:var(--muted); margin:0 0 .35rem; font-weight:600; }
.sub { color:var(--muted); margin:0 0 1rem; }
.charts { display:grid; grid-template-columns:1fr 1fr; gap:1rem; }
@media (max-width:700px) { .charts { grid-template-columns:1fr; } }
.chart-card { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:.75rem; }
.chart { width:100%; height:auto; display:block; touch-action:none; outline:none; }
.chart:focus-visible { box-shadow:0 0 0 2px var(--accent); border-radius:4px; }
.line { fill:none; stroke:var(--accent); stroke-width:2; }
.area { fill:var(--area); stroke:none; }
.bar { fill:var(--accent); transition:opacity .08s; }
.bar.dim { opacity:.4; }
.grid { stroke:var(--line); stroke-width:1; }
.axis { stroke:var(--line); stroke-width:1; }
.ylab, .xlab { fill:var(--muted); font-size:11px; }
.cross { stroke:var(--muted); stroke-width:1; stroke-dasharray:3 3; }
.dot { fill:var(--accent); stroke:var(--bg); stroke-width:1.5; }
table { border-collapse:collapse; width:100%; margin:.25rem 0 1rem; }
th,td { padding:.4rem .6rem; border-bottom:1px solid var(--line); text-align:right; }
th.l,td.l { text-align:left; } thead th { color:var(--muted); font-weight:600; }
.muted { color:var(--muted); } footer { margin-top:2.5rem; color:var(--muted); font-size:.85rem;
  border-top:1px solid var(--line); padding-top:1rem; }
a { color:var(--accent); }
.tt { position:fixed; pointer-events:none; z-index:10; display:none; white-space:nowrap;
  background:var(--card); border:1px solid var(--line); border-radius:6px; padding:.25rem .5rem;
  font-size:12px; color:var(--fg); box-shadow:0 2px 10px rgba(0,0,0,.18); transform:translate(-50%,-135%); }
.tt b { font-size:13px; font-weight:700; } .tt span { color:var(--muted); }
"""

# Inline crosshair/tooltip layer. Plain (non-f) string so JS braces stay literal.
_SCRIPT = """
(function () {
  var el = document.getElementById("chartdata");
  if (!el) return;
  var meta = JSON.parse(el.textContent), G = meta.geom;
  var tip = document.createElement("div"); tip.className = "tt"; document.body.appendChild(tip);
  function fmt(v) { return (Math.round(v * 100) / 100).toLocaleString(); }
  meta.charts.forEach(function (c) {
    var svg = document.getElementById(c.id); if (!svg) return;
    var n = c.y.length; if (!n) return;
    var hover = svg.querySelector(".hover"), cross = svg.querySelector(".cross");
    var dot = svg.querySelector(".dot"), bars = svg.querySelectorAll(".bar"), idx = -1;
    function xAt(i) {
      return c.type === "bar" ? G.ml + (i + 0.5) * (G.pl / n) : G.ml + i * (G.pl / Math.max(n - 1, 1));
    }
    function nearest(evt) {
      var pt = svg.createSVGPoint(); pt.x = evt.clientX; pt.y = evt.clientY;
      var p = pt.matrixTransform(svg.getScreenCTM().inverse());
      var rel = (p.x - G.ml) / G.pl;
      var i = c.type === "bar" ? Math.floor(rel * n) : Math.round(rel * (n - 1));
      return i < 0 ? 0 : (i > n - 1 ? n - 1 : i);
    }
    function show(i) {
      idx = i;
      var x = xAt(i);
      cross.setAttribute("x1", x); cross.setAttribute("x2", x);
      cross.setAttribute("y1", G.mt); cross.setAttribute("y2", G.mt + G.ph);
      if (dot) { dot.setAttribute("cx", x); dot.setAttribute("cy", G.mt + G.ph - (c.y[i] / c.top) * G.ph); }
      bars.forEach(function (b, bi) { b.classList.toggle("dim", bi !== i); });
      hover.style.display = "";
      tip.textContent = "";
      var b = document.createElement("b"); b.textContent = fmt(c.y[i]);
      var s = document.createElement("span"); s.textContent = " \\u00b7 " + c.x[i];
      tip.appendChild(b); tip.appendChild(s); tip.style.display = "block";
      var sp = svg.createSVGPoint(); sp.x = x; sp.y = G.mt;
      var scr = sp.matrixTransform(svg.getScreenCTM());
      tip.style.left = scr.x + "px"; tip.style.top = scr.y + "px";
    }
    function hide() {
      hover.style.display = "none"; tip.style.display = "none"; idx = -1;
      bars.forEach(function (b) { b.classList.remove("dim"); });
    }
    svg.addEventListener("pointermove", function (e) { show(nearest(e)); });
    svg.addEventListener("pointerleave", hide);
    svg.addEventListener("focus", function () { show(idx < 0 ? n - 1 : idx); });
    svg.addEventListener("blur", hide);
    svg.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      var i = (idx < 0 ? n : idx) + (e.key === "ArrowRight" ? 1 : -1);
      show(i < 0 ? 0 : (i > n - 1 ? n - 1 : i)); e.preventDefault();
    });
  });
})();
"""


def _e(text) -> str:
    return html.escape(str(text))


def _fmt(key: str, value: float) -> str:
    if key == "TOTAL_COST":
        return f"${value:,.2f}"
    return f"{value:,.0f}"


def _nice_top(ymax: float) -> float:
    """Round an axis maximum up to a clean 1/2/2.5/5/10 × 10ⁿ value."""
    if ymax <= 0:
        return 1.0
    exp = math.floor(math.log10(ymax))
    base = 10.0**exp
    for m in (1, 2, 2.5, 5, 10):
        if ymax <= m * base:
            return m * base
    return 10 * base


def _empty_svg(cid: str) -> str:
    return f'<svg id="{cid}" viewBox="0 0 {_CW} {_CH}" class="chart"></svg>'


def _axes_svg(x_labels, top: float, mode: str) -> str:
    parts = []
    # Y gridlines + value labels (0, mid, top).
    for frac in (0.0, 0.5, 1.0):
        gy = _MT + _PH - frac * _PH
        parts.append(f'<line x1="{_ML}" y1="{gy:.1f}" x2="{_ML + _PL}" y2="{gy:.1f}" class="grid"/>')
        parts.append(
            f'<text x="{_ML - 6}" y="{gy + 3:.1f}" class="ylab" text-anchor="end">'
            f"{_e(f'{round(top * frac):,}')}</text>"
        )
    # Baseline.
    parts.append(f'<line x1="{_ML}" y1="{_MT + _PH}" x2="{_ML + _PL}" y2="{_MT + _PH}" class="axis"/>')
    # X date labels (~6 evenly spaced ticks).
    n = len(x_labels)
    if n:
        step = max(1, round(n / 6))
        idxs = list(range(0, n, step))
        if idxs[-1] != n - 1:
            idxs.append(n - 1)
        for i in idxs:
            if mode == "bar":
                gx, anchor = _ML + (i + 0.5) * (_PL / n), "middle"
            else:
                gx = _ML + i * (_PL / max(n - 1, 1))
                anchor = "start" if i == 0 else ("end" if i == n - 1 else "middle")
            parts.append(
                f'<text x="{gx:.1f}" y="{_MT + _PH + 16}" class="xlab" '
                f'text-anchor="{anchor}">{_e(x_labels[i])}</text>'
            )
    return "".join(parts)


def _line_chart_svg(cid: str, x_labels, y) -> str:
    if not y:
        return _empty_svg(cid)
    top = _nice_top(max(y))
    n = len(y)
    dx = _PL / max(n - 1, 1)
    pts = [f"{_ML + i * dx:.1f},{_MT + _PH - (v / top) * _PH:.1f}" for i, v in enumerate(y)]
    line = " ".join(pts)
    area = f"{_ML},{_MT + _PH} " + line + f" {_ML + _PL},{_MT + _PH}"
    return (
        f'<svg id="{cid}" viewBox="0 0 {_CW} {_CH}" class="chart" tabindex="0" '
        f'role="img">{_axes_svg(x_labels, top, "line")}'
        f'<polygon points="{area}" class="area"/><polyline points="{line}" class="line"/>'
        f'<g class="hover" style="display:none"><line class="cross"/><circle class="dot" r="3.5"/></g>'
        f"</svg>"
    )


def _bar_chart_svg(cid: str, x_labels, y) -> str:
    if not y:
        return _empty_svg(cid)
    top = _nice_top(max(y))
    n = len(y)
    slot = _PL / n
    bw = slot * 0.62
    bars = []
    for i, v in enumerate(y):
        bh = (v / top) * _PH
        px = _ML + i * slot + (slot - bw) / 2
        py = _MT + _PH - bh
        bars.append(
            f'<rect x="{px:.1f}" y="{py:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
            f'class="bar" data-i="{i}"/>'
        )
    return (
        f'<svg id="{cid}" viewBox="0 0 {_CW} {_CH}" class="chart" tabindex="0" '
        f'role="img">{_axes_svg(x_labels, top, "bar")}{"".join(bars)}'
        f'<g class="hover" style="display:none"><line class="cross"/></g>'
        f"</svg>"
    )


def _daily_series(df_daily: pd.DataFrame, metric: str):
    if df_daily.empty:
        return [], []
    m = df_daily[df_daily["metric"] == metric]
    if m.empty:
        return [], []
    s = m.groupby("date")["value"].sum().sort_index()
    labels = [d.strftime("%b %d") if hasattr(d, "strftime") else str(d) for d in s.index]
    return labels, [float(v) for v in s.values]


def _count_charts(df_daily: pd.DataFrame):
    """Return (html, chart_data). Two charts (daily bar + cumulative area) per
    count metric, laid out 2 columns × 3 rows (one metric per row)."""
    blocks = []
    data = []
    for metric, label in COUNT_METRICS:
        labels, y = _daily_series(df_daily, metric)
        if not y:
            continue
        cum, run = [], 0.0
        for v in y:
            run += v
            cum.append(run)
        bar_id, area_id = f"c-{metric}-d", f"c-{metric}-c"
        blocks.append(
            f'<div class="chart-card"><h3>{_e(label)} — daily</h3>'
            f"{_bar_chart_svg(bar_id, labels, y)}</div>"
            f'<div class="chart-card"><h3>{_e(label)} — cumulative</h3>'
            f"{_line_chart_svg(area_id, labels, cum)}</div>"
        )
        data.append({"id": bar_id, "type": "bar", "x": labels, "y": y, "top": _nice_top(max(y))})
        data.append({"id": area_id, "type": "line", "x": labels, "y": cum, "top": _nice_top(max(cum))})
    if not blocks:
        return '<p class="muted">No temporal data in the selected window.</p>', []
    return '<div class="charts">' + "".join(blocks) + "</div>", data


def _snapshot_table(df_summary: pd.DataFrame) -> str:
    if df_summary is None or df_summary.empty:
        return '<p class="muted">No snapshot data.</p>'
    pivot = df_summary.pivot_table(
        index="project", columns="metric", values="value", aggfunc="sum", fill_value=0
    )
    head = "".join(f"<th>{_e(lbl)}</th>" for _, lbl in SNAPSHOT_COLUMNS)
    rows = []
    for project, row in pivot.iterrows():
        cells = [f'<td class="l">{_e(project)}</td>']
        for key, _lbl in SNAPSHOT_COLUMNS:
            v = float(row[key]) if key in pivot.columns else 0.0
            cells.append(f"<td>{_fmt(key, v)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        f'<table><thead><tr><th class="l">Project</th>{head}</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _magnitude_table(df_daily: pd.DataFrame, metric: str, label: str, is_cost: bool) -> str:
    if df_daily.empty:
        return ""
    m = df_daily[df_daily["metric"] == metric]
    if m.empty:
        return ""
    g = m.groupby(["project", "series"], dropna=False)["value"].sum().reset_index()
    rows = []
    for _, r in g.iterrows():
        val = float(r["value"])
        disp = f"${val:,.4f}" if is_cost else f"{val:,.0f}"
        series = _e(r["series"]) if r["series"] else "—"
        rows.append(
            f'<tr><td class="l">{_e(r["project"])}</td>'
            f'<td class="l">{series}</td><td>{disp}</td></tr>'
        )
    unit = "USD" if is_cost else "Tokens"
    return (
        f"<h3>{_e(label)}</h3><table><thead><tr>"
        f'<th class="l">Project</th><th class="l">Series</th><th>{unit}</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def render_html(
    *,
    workspace: str,
    window_start: datetime.date,
    window_end: datetime.date,
    generated: datetime.datetime,
    df_daily: pd.DataFrame,
    df_summary: pd.DataFrame,
) -> str:
    magnitude = "".join(
        _magnitude_table(df_daily, metric, label, is_cost)
        for metric, label, is_cost in MAGNITUDE_METRICS
    )
    charts_html, chart_data = _count_charts(df_daily)
    chart_json = json.dumps({"geom": _GEOM, "charts": chart_data})
    span_days = (window_end - window_start).days
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Opik usage — {_e(workspace)}</title>
<style>{_CSS}</style></head><body>
<h1>Opik usage — {_e(workspace)}</h1>
<p class="sub">Window: {_e(window_start)} → {_e(window_end)} (last {span_days} days) ·
 Generated: {_e(generated.date().isoformat())}</p>

<h2>Current snapshot (per project)</h2>
{_snapshot_table(df_summary)}

<h2>Usage over time</h2>
{charts_html}

<h2>Tokens &amp; cost</h2>
{magnitude or '<p class="muted">No token/cost data.</p>'}

<footer>
For cross-platform use-case <strong>growth &amp; adoption</strong> reporting
(Opik + EM + MPM), use cometx:
<a href="{COMETX_URL}">cometx admin growth-report</a>.
</footer>
<script type="application/json" id="chartdata">{chart_json}</script>
<script>{_SCRIPT}</script>
</body></html>"""


def write_report(
    path: str,
    *,
    workspace: str,
    window_start: datetime.date,
    window_end: datetime.date,
    generated: datetime.datetime,
    df_daily: pd.DataFrame,
    df_summary: pd.DataFrame,
) -> None:
    out = render_html(
        workspace=workspace,
        window_start=window_start,
        window_end=window_end,
        generated=generated,
        df_daily=df_daily,
        df_summary=df_summary,
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
