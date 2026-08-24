# DQMC performance report: Honeycomb Hubbard model

Public GitHub Pages site for the projective DQMC timing report on the Honeycomb Hubbard model.

- Site: <https://wangfh5.github.io/honeycomb-dqmc-benchmark/>
- After thermalization: <https://wangfh5.github.io/honeycomb-dqmc-benchmark/equilibrated.html>
- Paper: Fo-Hong Wang, Fanjie Sun, Cheng-Hao He, and Xiao Yan Xu, *Resolving Quantum Criticality in the Honeycomb Hubbard Model*, [arXiv:2602.03656](https://arxiv.org/abs/2602.03656)

This repository hosts the generated HTML and the publication-figure renderer. The simulation code and raw run data stay in a separate private repository.

## Publication figures

`make_benchmark_figures.py` reads the same embedded `DATA` object as `index.html`, so the static paper figures and the interactive report use one normalized data source. Install its pinned dependencies from `requirements-benchmark-figures.txt`; the virtual environment remains outside this repository in the private benchmark workflow.

The five-argument CLI takes `index.html`, followed by the output paths for the stacked benchmark, wide benchmark, speedup/stage-share, and Delay-T comparison PDFs. The report publication workflow writes them directly to:

- `/home/wangfh5/Sync/papers/submatrixLRpaper/FigS-production-benchmark.pdf`
- `/home/wangfh5/Sync/papers/submatrixLRpaper/rebuttal/decision1_reply/FigR-production-benchmark-wide.pdf`
- `/home/wangfh5/Sync/papers/submatrixLRpaper/rebuttal/decision1_reply/FigR-speedup-stage-shares.pdf`
- `/home/wangfh5/Sync/papers/submatrixLRpaper/rebuttal/decision1_reply/FigR-delayT-comparison.pdf`

Measured points use solid markers. Points whose `kind` is not `measured` use open markers and dotted extensions and are listed in the generation log.
