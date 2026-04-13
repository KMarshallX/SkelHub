
# AGENTS.md

## Project name

SkelHub

## Project purpose

SkelHub is a unified Python toolbox for:

1. integrating multiple 3D skeletonization algorithms under one framework
2. providing a common interface for running those algorithms on volumetric image data
3. evaluating skeleton quality using standardized geometric, topological, and task-relevant metrics
4. enabling reproducible comparisons between different skeletonization methods

The long-term goal is to make SkelHub a clean, extensible framework rather than a loose collection of unrelated scripts.

---

## Core design principle

Treat SkelHub as four clearly separated layers:

1. **Input / I/O layer**Read, validate, normalize, and write image volumes, masks, skeletons, graphs, and reports.
2. **Algorithm layer**Each skeletonization method lives in its own isolated backend and exposes a common SkelHub-facing interface.
3. **Evaluation layer**Evaluation must be algorithm-agnostic. It should consume standardized skeleton outputs and compute metrics consistently across methods.
4. **CLI / orchestration layer**The user interacts with SkelHub through one unified API and CLI, not through algorithm-specific ad hoc scripts.

Do not collapse these layers together.

---

## Initial scope

The first algorithm backend to support is the existing codebase, integrated as the first backend in SkelHub.

Initial SkelHub versions should focus on:

* one working algorithm backend: MCP
* one common result schema
* one shared configuration system
* one evaluation subsystem with a minimal but useful set of metrics
* one CLI entrypoint for running and evaluating methods

Do not over-expand the scope before these foundations are stable.

---

## High-level architecture

Target repository structure:

    SkelHub/
    ├── README.md
    ├── LICENSE
    ├── pyproject.toml
    ├── AGENTS.md
    ├── LOG.md
    ├── docs/
    ├── skelhub/
    │   ├── cli/
    │   ├── core/
    │   ├── io/
    │   ├── preprocessing/
    │   ├── algorithms/
    │   │   ├── mcp/
    │   │   ├── second_algo/
    │   │   └── third_algo/
    │   ├── postprocessing/
    │   ├── evaluation/
    │   ├── visualization/
    │   └── datasets/
    ├── tests/
    ├── examples/
    └── scripts/

---

## Immediate integration target: skeleton-mcp

The current repository (previous name - `skeleton-mcp`) should be integrated as the first algorithm backend, but not copied blindly.

### Required treatment

Refactor it into a backend under:

    skelhub/algorithms/mcp/

### Important constraints

* Do not preserve standalone repo quirks if they conflict with clean package design.
* Replace fragile script-style imports with proper package imports.
* Avoid naming collisions such as a local package named `io` that conflicts with Python stdlib.
* Preserve algorithmic behavior unless explicitly instructed to change it.
* If behavior changes are unavoidable, document them clearly.

### Goal

Expose MCP through a stable backend adapter, so that SkelHub can call it through a common framework interface.

---

## Common interface requirements

Every skeletonization backend must conform to a unified interface.

### Each backend should provide

* a unique algorithm name
* a config schema or validated parameter object
* a public `run(...)` entrypoint
* standardized output packaged in a shared result object

### Conceptual contract

Each algorithm backend should behave like:

    result = backend.run(
        volume=volume,
        mask=mask,
        spacing=spacing,
        config=config,
    )

### The returned result should support

* skeleton volume / skeleton mask
* metadata about run parameters
* runtime statistics
* warnings or failure flags
* backend-specific extras stored in a controlled metadata field

Do not let each backend invent its own incompatible return structure.

---

## Shared data model

Create shared framework-level result and config objects in `skelhub/core/`.

At framework-level, at least define the conceptual equivalents of:

* `VolumeData`
* `SkeletonResult`
* `GraphResult`
* `EvaluationResult`

These should be framework types, not tied to skeleton-mcp algorithm.

### SkeletonResult should be able to store

* algorithm name
* input metadata
* skeleton voxel output
* runtime stats
* warning list
* backend metadata
* optional graph output

Keep these structures explicit and typed wherever practical.

---

## Evaluation subsystem requirements

Evaluation must be a first-class subsystem, not an afterthought embedded in a single algorithm.

Create evaluation code under:

    skelhub/evaluation/

### TODO NOTE: Do not implement any evaluation metrics at this stage.

### Important design rule

Evaluation must consume the standardized `SkeletonResult`, not raw backend internals.

---

## Graph support

SkelHub should support both:

1. voxel skeleton outputs
2. graph representations derived from those outputs

Graph extraction should be treated as a distinct postprocessing stage as all skeletonization algortihms should not natively produce a graph.

Place graph conversion and graph cleanup code under:

    skelhub/postprocessing/

Do not entangle graphification with the core execution path unless necessary.

---

## CLI requirements

SkelHub should expose a unified CLI under `skelhub/cli/`.

Target commands should conceptually include:

* `skelhub run` - run specific algorithm
* `skelhub evaluate` - evaluate the output with ground truth
* `skelhub benchmark` - run selected algorithms against a dataset, then generate a benchmark reports

Examples of intended usage:

    skelhub run --algorithm mcp --input input.nii.gz --output out_dir/
    skelhub evaluate --pred pred_skel.nii.gz --ref ref_skel.nii.gz
    skelhub benchmark --algorithms mcp thinning teasar --dataset synthetic_set/

Do not expose algorithm-specific top-level scripts as the primary user workflow if they can be folded into the main CLI cleanly.

---

## Packaging and import rules

SkelHub must be a proper Python package.

### Requirements

* use `pyproject.toml`
* keep imports package-safe
* avoid sys.path hacks
* avoid relative-import fragility from script execution
* ensure the CLI can run after package installation

### Do not

* rely on executing files from arbitrary working directories
* depend on import side effects
* keep important behavior hidden in notebook-only code
* leave broken standalone entrypoints after refactors

---

## Implementation priorities

When implementing or refactoring, follow this order unless instructed otherwise:

* establish package structure
* define framework-level interfaces and result objects
* integrate `skeleton-mcp` as first backend
* create shared I/O utilities
* implement a placeholder evaluator
* add CLI
* add tests
* add more backends

Do not start integrating multiple algorithms or evaluation flow before the `skeleton-mcp` backend and shared abstractions are stable.

---

## Refactor policy

Refactoring must be conservative, traceable, and non-destructive.

### Rules

* preserve working behavior whenever possible
* prefer small modular patches over sweeping rewrites
* do not mix architectural refactor and algorithmic behavior changes in one step unless explicitly required
* after each meaningful refactor, keep the project runnable
* document moved, renamed, or replaced modules

### When consolidating code

* identify duplicated logic and centralize it carefully
* do not create over-generalized abstractions prematurely
* keep algorithm-specific code local to the backend unless it is truly shared

---

## Testing policy

Testing is mandatory for any substantial change.

Create tests under `tests/`.

### Minimum required test categories

1. **unit tests**

* result object behavior
* registry behavior
* config validation
* I/O utilities

2. **backend tests**

* `skeleton-mcp` backend runs successfully on small synthetic data (under /scratch/user/uqmxu4/Tools/SkelHub/test_data/small_test_data)
* `skeleton-mcp` backend output shape and type are correct
* backend metadata is populated correctly

3. **evaluation tests**

* the placehoder evaluation module output correct testing message (e.g., "Evaluation test")

4. **CLI smoke tests**

* basic run/evaluate commands execute without crashing

5. **regression tests**

* protect against previously fixed bugs where possible

---

## Documentation policy

Any significant structural change must update relevant documentation.

At minimum, keep the following in sync:

* `README.md`
* `docs/architecture.md`
* `docs/algorithms.md`
* `docs/evaluation.md`
* `LOG.md`

### The README should explain

* what SkelHub is
* supported algorithms
* installation
* CLI usage
* basic Python API usage
* output structure
* evaluation overview

### The LOG should record

* What has been changed (functionality and files)
* Any assumptions and tradeoffs during develoment
* Keep record in descending order (latest record comes first)
* Current date and time for every record

#### Important

* Before create the `README.md` for SkelHub, bump the current `README.md` which is for `skeleton-mcp` into `docs/algorithms.md`
* Keep the documentation concise but accurate, avoid using jargons and fillers. Preferbly, use bulletpoints or other hierarchical notation to explain complicated concepts.

---

## Coding style guidance

* prefer readable, modular Python
* use clear function and class boundaries
* use explicit naming over cryptic abbreviations
* keep backend adapters thin
* isolate framework-level abstractions from backend internals
* use type hints where practical
* add concise docstrings to public functions and classes

Avoid deeply nested control flow where cleaner decomposition is possible.

---

## Performance guidance

Performance matters, but correctness and stable architecture come first.

### Prefer this order

1. correctness
2. interface stability
3. maintainability
4. performance optimization

When optimizing:

* do not silently change mathematical output unless explicitly allowed
* benchmark before and after
* keep optimizations localized
* document assumptions and tradeoffs

---

## Error handling

SkelHub should fail clearly, not mysteriously.

### Required behavior

* validate inputs early
* raise informative errors for malformed volumes, masks, configs, or incompatible dimensions
* expose warnings for degraded but still usable runs
* avoid silent fallback behavior unless explicitly designed and documented

---

## Dependencies

Keep dependencies lean and purposeful.

### General rule

Only add a dependency when it clearly improves:

* correctness
* maintainability
* interoperability
* user experience

Avoid unnecessary framework bloat in the initial implementation.

---

## Skeleton-mcp backened-specific guidance

When integrating the `skeleton-mcp` method:

* preserve the mathematical behavior of the original implementation unless explicitly changing it
* isolate `skeleton-mcp`-specific logic under `skelhub/algorithms/mcp/`
* do not leak `skeleton-mcp` assumptions into the framework core
* wrap `skeleton-mcp` with an adapter rather than bending the framework around `skeleton-mcp`
* migrate any reusable parts only if they are genuinely algorithm-agnostic

If the original repo contains fragile workarounds, replace them with clean package-safe equivalents and document the change.

---

## Extension policy for future algorithms

Future algorithms such as thinning-based, TEASAR-like, or other graph-centered methods should be added as new backend modules under:

    skelhub/algorithms/`<name>`/

Each new backend must:

* implement the common interface
* register cleanly in the algorithm registry
* provide its own config handling
* pass backend-specific tests
* document assumptions and limitations

Do not hard-code special cases into the framework core for each new algorithm.

---

## Deliverable expectations for coding tasks

When completing a development task, the record should include:

1. summary of what was changed
2. files added, removed, or modified
3. architecture decisions made
4. assumptions
5. limitations
6. tests run
7. remaining risks or recommended next steps

Do not claim completion without identifying assumptions and limitations.

Keep the record easy-read, accurate and concise in LOG.md.

---

## What not to do

* do not treat SkelHub as a dump of unrelated repos
* do not hard-wire framework logic to `skeleton-mcp`-specific internals
* do not leave script-only execution paths as the only supported workflow
* do not duplicate evaluation logic across algorithms
* do not introduce broad destructive refactors without necessity
* do not expand to many algorithms before the first backend is clean and stable
* do not skip tests after structural changes
* do not leave docs stale after major implementation changes

---

## Final principle

SkelHub should become a coherent skeletonization framework with shared abstractions, not merely a wrapper around one algorithm.

Whenever there is tension between short-term convenience and long-term modularity, prefer the design that keeps:

* interfaces clean
* backends isolated
* evaluation reusable
* the repository maintainable
