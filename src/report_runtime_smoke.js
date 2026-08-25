#!/usr/bin/env node
"use strict";

const fs = require("fs");

if (process.argv.length !== 3) {
  throw new Error("usage: node report_runtime_smoke.js <benchmark_report.html>");
}

const html = fs.readFileSync(process.argv[2], "utf8");
const repositoryUrl = "https://github.com/wangfh5/honeycomb-dqmc-benchmark";
const repositoryLinks = [...html.matchAll(new RegExp(`<a[^>]+href=["']${repositoryUrl}["']`, "g"))];
if (repositoryLinks.length !== 1) throw new Error(`expected one report-repository link, found ${repositoryLinks.length}`);
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]);
if (scripts.length !== 1) throw new Error(`expected one inline script, found ${scripts.length}`);
const dataMatch = scripts[0].match(/const DATA = ([\s\S]*?);\n\s*const SVG_NS/);
if (!dataMatch) throw new Error("cannot extract report payload");
const data = JSON.parse(dataMatch[1]);

class MockElement {
  constructor(tagName, id = "") {
    this.tagName = tagName;
    this.id = id;
    this.children = [];
    this.attributes = {};
    this.style = {};
    this.classList = {add() {}, remove() {}};
    this.clientWidth = 980;
    this.value = "";
    this.selected = false;
    this.textContent = "";
    this.innerHTML = "";
    this.listeners = {};
  }

  setAttribute(key, value) {
    this.attributes[key] = value;
  }

  append(...children) {
    this.children.push(...children);
    if (this.tagName === "select") {
      const selected = children.find(child => child && child.selected);
      if (selected) this.value = selected.value;
    }
  }

  replaceChildren(...children) {
    this.children = [...children];
  }

  addEventListener(type, listener) {
    this.listeners[type] = listener;
  }

  dispatch(type) {
    if (this.listeners[type]) this.listeners[type]({type});
  }
}

const elements = new Map();
for (const id of ["report-title", "report-state", "report-state-title", "report-state-copy", "report-lead", "report-lead-list", "report-params", "report-footer", "speedup-copy", "acceptance-copy", "utilization-copy", "generated-at", "summary", "update-chart", "sweep-chart", "speedup-chart", "nublock-chart", "acceptance-panel", "acceptance-chart", "utilization-panel", "utilization-chart", "stage-chart", "stage-detail", "tooltip"]) {
  elements.set(id, new MockElement("div", id));
}
elements.set("speedup-metric", Object.assign(new MockElement("select", "speedup-metric"), {value: "update_seconds"}));
elements.set("utilization-metric", Object.assign(new MockElement("select", "utilization-metric"), {value: "cpu_percent"}));
elements.set("stage-algorithm", new MockElement("select", "stage-algorithm"));
elements.set("split-update", Object.assign(new MockElement("input", "split-update"), {type: "checkbox", checked: false}));

const document = {
  createElement: tagName => new MockElement(tagName),
  createElementNS: (_namespace, tagName) => new MockElement(tagName),
  createTextNode: text => Object.assign(new MockElement("#text"), {textContent: text}),
  getElementById: id => elements.get(id)
};
const window = {addEventListener() {}, clearTimeout, setTimeout};
new Function("document", "window", scripts[0])(document, window);

const expectedInitialState = data.report_mode === "equilibrated" ? "Production-equilibrated restart" : "Random auxiliary-field configuration";
if (elements.get("report-state").hidden !== false) throw new Error("initial-state banner is hidden");
if (elements.get("report-state-title").textContent !== expectedInitialState) throw new Error(`initial-state title is ${elements.get("report-state-title").textContent}, expected ${expectedInitialState}`);
const summaryCards = elements.get("summary").children.filter(element => element instanceof MockElement && element.tagName === "article");
if (summaryCards.length !== 4) throw new Error(`summary has ${summaryCards.length} cards, expected 4`);
const summaryMarkup = summaryCards.map(card => card.innerHTML).join("\n");
const expectedSweepSummaries = data.points.some(point => point.algorithm === "fast") ? 2 : 1;
const actualSweepSummaries = (summaryMarkup.match(/sweep time/gi) || []).length;
if (actualSweepSummaries !== expectedSweepSummaries) throw new Error(`summary has ${actualSweepSummaries} sweep-time metrics, expected ${expectedSweepSummaries}`);
if (data.points.some(point => point.kind === "estimated" && point.update_seconds > 0) && !summaryMarkup.includes("Estimated update time")) {
  throw new Error("summary does not identify the estimated update-time peak");
}

function descendants(element) {
  return element.children.flatMap(child => child instanceof MockElement ? [child, ...descendants(child)] : []);
}

function count(containerId, tagName, role) {
  return descendants(elements.get(containerId)).filter(element => element.tagName === tagName && (!role || element.attributes["data-role"] === role)).length;
}

function findToggle(containerId, algorithmId) {
  const input = descendants(elements.get(containerId)).find(element => element.tagName === "input" && element.attributes["data-algorithm"] === algorithmId);
  if (!input) throw new Error(`missing ${algorithmId} toggle in ${containerId}`);
  return input;
}

function toggleSeries(containerId, algorithmId, checked) {
  const input = findToggle(containerId, algorithmId);
  input.checked = checked;
  input.dispatch("change");
}

function svgDomain(containerId) {
  const svg = descendants(elements.get(containerId)).find(element => element.tagName === "svg");
  if (!svg) throw new Error(`missing svg in ${containerId}`);
  return {ymin: Number(svg.attributes["data-ymin"]), ymax: Number(svg.attributes["data-ymax"])};
}

function closeEnough(actual, expected, label) {
  if (!Number.isFinite(actual) || Math.abs(actual - expected) > 1e-9 * Math.max(1, Math.abs(expected))) {
    throw new Error(`${label}: ${actual}, expected ${expected}`);
  }
}

function requireCount(containerId, tagName, role, expected) {
  const actual = count(containerId, tagName, role);
  if (actual !== expected) throw new Error(`${containerId} ${role || tagName}: ${actual}, expected ${expected}`);
}

function ranges(metric) {
  return data.points.filter(point => point[metric] > 0 && point[`${metric}_max`] > point[`${metric}_min`]).length;
}

function utilizationRanges(metric) {
  return data.resource_efficiency.filter(point => point[`${metric}_max`] > point[`${metric}_min`]).length;
}

function speedupPoints(metric) {
  const sampleKey = metric.replace("_seconds", "");
  const baseline = new Map(data.points.filter(point => point.algorithm === "sublr").map(point => [point.L, point]));
  return data.points.filter(point => point.algorithm !== "sublr" && point[metric] > 0 && point.sample_values[sampleKey].length && baseline.has(point.L)).map(point => {
    const reference = baseline.get(point.L);
    const ratios = point.sample_values[sampleKey].flatMap(comparator => reference.sample_values[sampleKey].map(base => comparator / base));
    return {low: Math.min(...ratios), high: Math.max(...ratios)};
  });
}

const chartIds = ["update-chart", "sweep-chart", "speedup-chart", "nublock-chart", "stage-chart"];
if (data.report_mode === "equilibrated") chartIds.splice(4, 0, "acceptance-chart");
if (data.resource_efficiency.length) chartIds.splice(4, 0, "utilization-chart");
for (const id of chartIds) requireCount(id, "svg", "", 1);
const updatePoints = data.points.filter(point => point.update_seconds > 0);
const updateAlgorithms = new Set(updatePoints.map(point => point.algorithm));
requireCount("update-chart", "circle", "data-point", updatePoints.length);
requireCount("sweep-chart", "circle", "data-point", data.points.filter(point => point.sweep_seconds > 0).length);
const estimatedSweeps = data.points.filter(point => point.kind === "estimated" && point.sweep_seconds > 0);
const estimatedUpdates = data.points.filter(point => point.kind === "estimated" && point.update_seconds > 0);
requireCount("update-chart", "path", "estimate-line", estimatedUpdates.length ? 1 : 0);
requireCount("sweep-chart", "path", "estimate-line", estimatedSweeps.length ? 1 : 0);
requireCount("update-chart", "div", "estimate-key", estimatedUpdates.length ? 1 : 0);
requireCount("sweep-chart", "div", "estimate-key", estimatedSweeps.length ? 1 : 0);
const estimatedUpdateMarkers = descendants(elements.get("update-chart")).filter(element => element.tagName === "circle" && element.attributes["data-kind"] === "estimated");
if (estimatedUpdateMarkers.length !== estimatedUpdates.length) throw new Error(`update chart has ${estimatedUpdateMarkers.length} estimated markers, expected ${estimatedUpdates.length}`);
const estimatedMarkers = descendants(elements.get("sweep-chart")).filter(element => element.tagName === "circle" && element.attributes["data-kind"] === "estimated");
if (estimatedMarkers.length !== estimatedSweeps.length) throw new Error(`sweep chart has ${estimatedMarkers.length} estimated markers, expected ${estimatedSweeps.length}`);
requireCount("update-chart", "line", "error-bar", 3 * ranges("update_seconds"));
requireCount("sweep-chart", "line", "error-bar", 3 * ranges("sweep_seconds"));
requireCount("update-chart", "input", "series-toggle", updateAlgorithms.size);
if (data.report_mode === "equilibrated") {
  const acceptancePoints = data.acceptance_series.flatMap(series => series.points);
  const acceptanceRanges = acceptancePoints.filter(point => point.high > point.low).length;
  requireCount("acceptance-chart", "path", "series-line", data.acceptance_series.length);
  requireCount("acceptance-chart", "circle", "data-point", acceptancePoints.length);
  requireCount("acceptance-chart", "line", "error-bar", 3 * acceptanceRanges);
  requireCount("acceptance-chart", "input", "series-toggle", data.acceptance_series.length);
}
const speedups = speedupPoints("update_seconds");
requireCount("speedup-chart", "circle", "data-point", speedups.length);
requireCount("speedup-chart", "line", "error-bar", 3 * speedups.filter(point => point.high > point.low).length);
requireCount("speedup-chart", "path", "estimate-line", estimatedUpdates.length ? 1 : 0);
requireCount("speedup-chart", "div", "estimate-key", estimatedUpdates.length ? 1 : 0);
if (estimatedSweeps.length) {
  elements.get("speedup-metric").value = "sweep_seconds";
  elements.get("speedup-metric").dispatch("change");
  requireCount("speedup-chart", "circle", "data-point", speedupPoints("sweep_seconds").length);
  requireCount("speedup-chart", "path", "estimate-line", 1);
  requireCount("speedup-chart", "div", "estimate-key", 1);
  elements.get("speedup-metric").value = "update_seconds";
  elements.get("speedup-metric").dispatch("change");
}
const repeated = data.points.filter(point => point.algorithm !== "fast");
requireCount("nublock-chart", "circle", "data-point", repeated.length);
if (data.resource_efficiency.length) {
  const utilizationAlgorithms = new Set(data.resource_efficiency.map(point => point.algorithm));
  requireCount("utilization-chart", "path", "series-line", utilizationAlgorithms.size);
  requireCount("utilization-chart", "circle", "data-point", data.resource_efficiency.length);
  requireCount("utilization-chart", "line", "error-bar", 3 * utilizationRanges("cpu_percent"));
  requireCount("utilization-chart", "input", "series-toggle", utilizationAlgorithms.size);
  elements.get("utilization-metric").value = "memory_percent";
  elements.get("utilization-metric").dispatch("change");
  requireCount("utilization-chart", "circle", "data-point", data.resource_efficiency.length);
  requireCount("utilization-chart", "line", "error-bar", 3 * utilizationRanges("memory_percent"));
} else {
  requireCount("utilization-chart", "svg", "", 0);
}
if (updateAlgorithms.has("fast")) {
  const visibleWithoutFast = updatePoints.filter(point => point.algorithm !== "fast");
  const visibleValues = visibleWithoutFast.flatMap(point => [point.update_seconds_min ?? point.update_seconds, point.update_seconds, point.update_seconds_max ?? point.update_seconds]).filter(value => value > 0);
  toggleSeries("update-chart", "fast", false);
  requireCount("update-chart", "circle", "data-point", visibleWithoutFast.length);
  const domain = svgDomain("update-chart");
  closeEnough(domain.ymin, 10 ** (Math.log10(Math.min(...visibleValues)) - 0.08), "update ymin without Fast");
  closeEnough(domain.ymax, 10 ** (Math.log10(Math.max(...visibleValues)) + 0.08), "update ymax without Fast");
  toggleSeries("update-chart", "fast", true);
  requireCount("update-chart", "circle", "data-point", updatePoints.length);
}

const speedupIds = [...new Set(data.points.filter(point => point.algorithm !== "sublr").map(point => point.algorithm))];
if (speedupIds.includes("delaylr")) {
  for (const algorithmId of speedupIds) toggleSeries("speedup-chart", algorithmId, algorithmId === "delaylr");
  const speedupSvg = descendants(elements.get("speedup-chart")).find(element => element.tagName === "svg");
  const majorTicks = Number(speedupSvg.attributes["data-major-ticks"]);
  const minorTicks = Number(speedupSvg.attributes["data-minor-ticks"]);
  const labels = descendants(elements.get("speedup-chart")).filter(element => element.attributes["data-role"] === "y-tick-label");
  if (majorTicks < 4) throw new Error(`speedup major ticks after isolating Delay-T: ${majorTicks}`);
  if (minorTicks < 3) throw new Error(`speedup minor ticks after isolating Delay-T: ${minorTicks}`);
  if (labels.length !== majorTicks) throw new Error(`speedup labeled ${labels.length} of ${majorTicks} major ticks`);
  const values = labels.map(label => Number(label.attributes["data-tick-value"])).filter(Number.isFinite);
  const step = values.slice(1).reduce((smallest, value, index) => Math.min(smallest, value - values[index]), Infinity);
  const domainRatio = Number(speedupSvg.attributes["data-ymax"]) / Number(speedupSvg.attributes["data-ymin"]);
  if (!(step > 0)) throw new Error(`speedup major step after isolating Delay-T: ${step}`);
  if (domainRatio < 5 && step > 0.5 + 1e-9) throw new Error(`speedup major step ${step} is too coarse for domain ratio ${domainRatio}`);
  for (const algorithmId of speedupIds) toggleSeries("speedup-chart", algorithmId, true);
}
const selectedStages = data.points.filter(point => point.algorithm === "sublr");
requireCount("stage-chart", "rect", "stage-segment", selectedStages.length * data.stages.length);
requireCount("stage-chart", "rect", "update-gfunc", 0);
requireCount("stage-chart", "line", "update-split", 0);
if (selectedStages.some(point => point.update_parts)) {
  const split = elements.get("split-update");
  split.checked = true;
  split.dispatch("change");
  requireCount("stage-chart", "rect", "update-gfunc", selectedStages.length);
  requireCount("stage-chart", "line", "update-split", selectedStages.length);
  const stageLabels = descendants(elements.get("stage-chart")).filter(element => element.tagName === "text" && element.attributes["data-role"] === "stage-label");
  if (stageLabels.some(label => !String(label.textContent).endsWith("%"))) {
    throw new Error(`stage labels must include %: ${stageLabels.map(label => label.textContent).join(", ")}`);
  }
  const first = selectedStages.find(point => point.update_parts);
  if (first) {
    const gfuncShare = 100 * first.update_parts.gfunc / first.stage_total_seconds;
    const gfuncHeight = (gfuncShare / 100) * (440 - 35 - 50);
    if (gfuncHeight >= 12) {
      const gfuncLabel = stageLabels.find(label => Number(label.attributes["data-L"]) === first.L && label.attributes["data-part"] === "update-gfunc");
      if (!gfuncLabel) throw new Error(`missing split-update label for L=${first.L} update-T/G (${gfuncShare.toFixed(1)}%)`);
    }
  }
  split.checked = false;
  split.dispatch("change");
  requireCount("stage-chart", "rect", "update-gfunc", 0);
}
if (data.points.some(point => point.algorithm === "fast")) {
  elements.get("stage-algorithm").value = "fast";
  elements.get("stage-algorithm").dispatch("change");
  requireCount("stage-chart", "rect", "update-gfunc", 0);
  requireCount("stage-chart", "line", "update-split", 0);
  elements.get("stage-algorithm").value = "sublr";
  elements.get("stage-algorithm").dispatch("change");
}
console.log(`PASS runtime rendered ${chartIds.length} SVG charts and ${repeated.length} nublock points${data.resource_efficiency.length ? ", including CPU/memory utilization switching" : ""}`);
