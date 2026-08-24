# DQMC performance report: Honeycomb Hubbard model

Public GitHub Pages site for the projective DQMC timing report on the Honeycomb Hubbard model.

- Site: <https://wangfh5.github.io/honeycomb-dqmc-benchmark/>
- After thermalization: <https://wangfh5.github.io/honeycomb-dqmc-benchmark/equilibrated.html>
- Paper: Fo-Hong Wang, Fanjie Sun, Cheng-Hao He, and Xiao Yan Xu, *Resolving Quantum Criticality in the Honeycomb Hubbard Model*, [arXiv:2602.03656](https://arxiv.org/abs/2602.03656)

This repository hosts the generated HTML and the publication-figure renderer. The simulation code and raw run data stay in a separate private repository.

## Publication figures

`paper_figures/` contains the script that renders the static paper figures from the same embedded `DATA` as `index.html`, so the paper figures and the interactive report share one normalized data source.

Measured points use solid markers; non-measured points use open markers with dotted extensions.

Dependencies: `paper_figures/requirements-benchmark-figures.txt`.
