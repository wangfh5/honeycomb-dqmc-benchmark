# DQMC performance report: Honeycomb Hubbard model

Public GitHub Pages site for the projective DQMC timing report on the Honeycomb Hubbard model.

- Site: <https://wangfh5.github.io/honeycomb-dqmc-benchmark/>
- After thermalization: <https://wangfh5.github.io/honeycomb-dqmc-benchmark/equilibrated.html>
- Paper: Fo-Hong Wang, Fanjie Sun, Cheng-Hao He, and Xiao Yan Xu, *Resolving Quantum Criticality in the Honeycomb Hubbard Model*, [arXiv:2602.03656](https://arxiv.org/abs/2602.03656)

This repository hosts the generated HTML, normalized public data, and report/figure renderers. The simulation code and raw run data stay in a separate private repository.

## Report sources

`data/` contains the normalized public JSON payloads embedded byte-for-byte in `index.html` and `equilibrated.html`. `src/render_report.py` combines either payload with `src/report_template.html`, while `src/report_runtime_smoke.js` checks the resulting interactive charts.

## Publication figures

`paper_figures/` contains the script that renders the static paper figures from `data/report_data.json`, the same normalized payload embedded in `index.html`.

All four figures follow the legacy benchmark style: Arial regular text, inward ticks on all sides, light grids, and the same algorithm colors and markers; the stacked and wide time panels use solid filled measured points, while non-measured points remain open with dotted extensions.

Dependencies: `paper_figures/requirements-benchmark-figures.txt`.
