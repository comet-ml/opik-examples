// Comet JavaScript panel: downstream verdict accuracy per class, one bar group per registered
// training run. Runs inside Comet; scripts/10_em_dashboard.py stores this file in the project view.
class MyPanel extends Comet.Panel {
  async draw(experimentKeys, projectId) {
    const classes = ["blocked", "partial", "clear"];
    const byName = (list) =>
      Object.fromEntries((Array.isArray(list) ? list : []).map((entry) => [entry.name, entry.valueCurrent]));
    const runs = [];
    let reference = null;
    for (const key of experimentKeys) {
      const others = byName(await this.api.experimentOther(key));
      if (!others.registry_model) continue;
      const metrics = byName(await this.api.experimentMetricsSummary(key));
      if (metrics.opik_verdict_accuracy === undefined) continue;
      if (others.opik_vlm_only_accuracy !== undefined) reference = Number(others.opik_vlm_only_accuracy);
      runs.push({
        version: others.registry_model.split(":").pop(),
        map50: Number(metrics["metrics/mAP50(B)"]),
        values: [metrics.opik_verdict_accuracy, ...classes.map((c) => metrics["opik_accuracy_" + c])].map(Number),
      });
    }
    if (runs.length === 0) {
      this.print("<p>No registered training run with Opik results among the experiments on this page.</p>");
      return;
    }
    runs.sort((a, b) => a.version.localeCompare(b.version, undefined, { numeric: true }));
    const labels = ["all classes", ...classes];
    const data = runs.map((run) => ({
      type: "bar",
      name: "detector " + run.version + " (mAP50 " + run.map50.toFixed(3) + ")",
      x: labels,
      y: run.values,
    }));
    if (reference !== null) {
      data.unshift({ type: "bar", name: "no detector (vlm_only)", x: ["all classes"], y: [reference] });
    }
    this.plot({
      data: data,
      layout: {
        barmode: "group",
        yaxis: { title: "verdict accuracy (Opik)", range: [0, 1] },
        legend: { orientation: "h" },
      },
    });
  }
}
