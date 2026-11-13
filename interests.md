# Research interests

<!--
Steers deep-dive and roundup selection (arxiv_podcast/score.py). The whole
file goes to the scoring model once per episode. It's ~500 tokens next to
~25k tokens of abstracts, so precision matters far more than brevity here.
Tune with: uv run python -m arxiv_podcast.score
The score bands below line up with RELEVANCE_THRESHOLD=6 (on-interest).
-->

Numerical analyst working on finite element methods for PDEs on surfaces
and in moving or evolving domains, and on computational mechanics of
slender bodies, with applications in biology and biomechanics.

## Core interests (score 8-10)

- Surface finite element methods: evolving surface FEM (ESFEM), PDEs on
  stationary or moving curved surfaces, surface/geometric approximation.
- PDEs in evolving or time-dependent domains: arbitrary Lagrangian-Eulerian
  (ALE) methods, moving meshes, evolving interfaces, free boundary problems.
- Coupled bulk-surface PDEs, and reaction-diffusion on surfaces.
- Unfitted and cut methods for surface/interface problems: CutFEM, TraceFEM,
  unfitted discontinuous Galerkin.
- A priori and a posteriori error analysis, and stability of such schemes.
- Phase-field models on and for surfaces, e.g. Cahn-Hilliard and Allen-Cahn.
- Cosserat rods, Kirchhoff rods and slender-body models: discretisation,
  stability, low-inertia or viscous-dominated dynamics.
- PDE-constrained optimal control and inverse problems, especially
  reconstructing shapes or motion from imaging data.
- Locomotion and biomechanics models (undulatory swimming, C. elegans,
  low-Reynolds-number fluid-structure interaction).

## Related interests (score 6-7)

- Geometric PDEs and geometric flows (mean curvature, Willmore), shape
  optimisation, and optimal partition problems.
- Finite element methods for PDEs with random data, and uncertainty
  quantification in evolving domains.
- Space-time and structure-preserving discretisations of time-dependent
  PDEs (energy-stable, conservative).
- Numerical methods for mathematical biology, such as cell motility, tissue
  mechanics and pattern formation.
- Computer vision or imaging pipelines that use PDE or FEM models.

## Applications of interest: UKRI priority areas (score 6-8 when the numerics overlap the topics above, otherwise 3-5)

- Advanced materials: phase-field and microstructure evolution, thin films,
  membranes, multiphase and interface problems, homogenisation.
- Manufacturing: additive manufacturing (melt pool, moving fronts), digital
  twins, process simulation with moving boundaries.
- Environment and climate: geophysical flows on the sphere, ice sheets and
  glaciers, sea ice, porous media and subsurface flow, transport and
  dispersion of pollutants.
- Engineering biology and health: biomechanics, morphogenesis, and
  reduced-order or data-driven models of living systems.
- AI for science: scientific machine learning, neural operators and
  learned solvers, but only where there is genuine numerical analysis
  content (convergence, stability, error bounds).
- Quantum computing algorithms and tensor-network methods.

## De-prioritise (score 0-3 unless strongly tied to the above)

- Numerical linear algebra and solvers studied in isolation (eigenvalue
  algorithms, randomised linear algebra, preconditioners with no PDE
  application).
- Pure approximation theory, quadrature, and special functions.
- Stochastic differential equations or ODE time-stepping theory with no
  spatial or geometric component.
- Purely empirical machine learning with no numerical analysis.
