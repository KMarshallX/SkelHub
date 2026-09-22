"""Algorithm-independent topology summaries for GraphML and skeleton NIfTI."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Callable

import igraph as ig

from skelhub.postprocessing.graphgen.api import generate_graphml_from_nifti

Progress = Callable[[int | None, str], None]
Summary = Callable[[dict[str, object]], None]


@dataclass(frozen=True)
class TopologyResult:
    input_path: str
    graph_path: str
    graph_source: str
    cache_hit: bool
    components: int
    nodes: int
    edges: int
    independent_cycles: int
    degree_distribution: dict[int, int]
    cycle_vertices_distribution: dict[int, int]
    method: str = "complete unweighted minimum cycle basis"
    igraph_version: str = ig.__version__
    warnings: tuple[str, ...] = ()

    def as_report(self) -> dict:
        """Return JSON-compatible statistics and provenance."""
        return asdict(self)

    @classmethod
    def from_report(cls, report: dict) -> "TopologyResult":
        """Rebuild a typed result from the JSON process protocol."""
        values = dict(report)
        for name in ("degree_distribution", "cycle_vertices_distribution"):
            values[name] = {int(key): int(count) for key, count in values[name].items()}
        values["warnings"] = tuple(values.get("warnings", ()))
        return cls(**values)


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _graphgen_digest() -> str:
    directory = Path(__file__).resolve().parents[1] / "postprocessing" / "graphgen"
    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(_file_digest(path).encode())
    return digest.hexdigest()


def cached_graph_for_nifti(source: str | Path, cache_dir: Path | None = None, progress: Progress | None = None) -> tuple[Path, bool]:
    """Return a content-keyed GraphML, generating and publishing it atomically."""
    source = Path(source).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    if progress:
        progress(None, f"Hashing skeleton NIfTI for graph cache: {source.name}")
    cache_root = cache_dir or Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "skelhub" / "graphgen"
    key = hashlib.sha256(f"{_file_digest(source)}:{_graphgen_digest()}:graphgen-default-v1".encode()).hexdigest()
    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / f"{key}.graphml"
    if target.is_file():
        try:
            ig.Graph.Read_GraphML(str(target))
            if progress:
                progress(42, "Valid cached graph found; graphgen conversion skipped")
            return target, True
        except Exception:
            target.unlink()
    with tempfile.NamedTemporaryFile(prefix=f".{key}-", suffix=".graphml", dir=cache_root, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        if progress:
            progress(None, "Cache miss; generating proto-graph from skeleton volume")
        generate_graphml_from_nifti(source, temporary, log=(lambda message: progress(None, message)) if progress else None)
        ig.Graph.Read_GraphML(str(temporary))
        os.replace(temporary, target)
        if progress:
            progress(45, f"Derived GraphML cached: {target.name}")
    finally:
        temporary.unlink(missing_ok=True)
    return target, False


def analyze_graph(graph: ig.Graph, *, input_path: str = "", graph_path: str = "", graph_source: str = "GraphML", cache_hit: bool = False, progress: Progress | None = None, summary: Summary | None = None) -> TopologyResult:
    """Summarize the exact undirected input multigraph."""
    if graph.is_directed():
        raise ValueError("TopoStats requires an undirected GraphML graph.")
    if progress:
        progress(60, f"Loaded graph: {graph.vcount()} nodes, {graph.ecount()} edges")
    components = len(graph.connected_components())
    cycles = graph.ecount() - graph.vcount() + components
    degree_distribution = dict(sorted(Counter(graph.degree(loops=True)).items()))
    if progress:
        progress(72, f"Counted {components} components and {cycles} independent cycles")
        progress(None, "Computing complete unweighted minimum cycle basis")
    if summary:
        summary({
            "components": components,
            "nodes": graph.vcount(),
            "edges": graph.ecount(),
            "independent_cycles": cycles,
            "degree_distribution": degree_distribution,
        })
    basis = graph.minimum_cycle_basis(cutoff=None, weights=None)
    if len(basis) != cycles:
        raise RuntimeError("Minimum cycle basis size does not match the independent cycle count.")
    sizes: Counter[int] = Counter()
    for edge_ids in basis:
        vertices = {vertex for edge_id in edge_ids for vertex in graph.es[edge_id].tuple}
        sizes[len(vertices)] += 1
    if progress:
        progress(95, f"Cycle basis complete: {len(basis)} cycles; degree and cycle histograms ready")
    return TopologyResult(
        input_path=input_path, graph_path=graph_path, graph_source=graph_source,
        cache_hit=cache_hit, components=components, nodes=graph.vcount(), edges=graph.ecount(),
        independent_cycles=cycles, degree_distribution=degree_distribution,
        cycle_vertices_distribution=dict(sorted(sizes.items())),
    )


def analyze_path(path: str | Path, cache_dir: Path | None = None, progress: Progress | None = None, summary: Summary | None = None) -> TopologyResult:
    """Analyze GraphML directly or a skeleton NIfTI through cached graphgen."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() == ".graphml":
        if progress:
            progress(25, f"Reading GraphML input: {source.name}")
        graph_path, hit, kind = source, False, "GraphML input"
    elif source.name.lower().endswith((".nii", ".nii.gz")):
        graph_path, hit, kind = (*cached_graph_for_nifti(source, cache_dir, progress), "cached graphgen output")
    else:
        raise ValueError("TopoStats input must be GraphML or skeleton NIfTI (.nii or .nii.gz).")
    graph = ig.Graph.Read_GraphML(str(graph_path))
    return analyze_graph(graph, input_path=str(source.resolve()), graph_path=str(graph_path), graph_source=kind, cache_hit=hit, progress=progress, summary=summary)
