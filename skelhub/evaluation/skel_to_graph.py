"""
Standalone 3D centreline-volume to GraphML pipeline.
"""

from __future__ import annotations

import argparse
import os
from math import ceil, log
from time import perf_counter as pf

import igraph as ig
import nibabel
import numpy as np
from geomdl import knotvector
from numba import njit, prange
from scipy import interpolate
from skimage.io import imread


def _log(message: str, verbose: bool) -> None:
    if verbose:
        print(message)


def _load_volume(input_path: str) -> tuple[np.ndarray, np.ndarray]:
    ext = os.path.splitext(input_path)[1].lower()

    if ext in {".nii", ".gz"}:
        proxy = nibabel.load(input_path)
        volume = proxy.dataobj.get_unscaled().transpose()
        if volume.ndim == 4:
            volume = volume[0]
        zooms = np.array(proxy.header.get_zooms()[:3], dtype=float)
        resolution = np.flip(zooms) if zooms.size == 3 else np.ones(3, dtype=float)
    else:
        volume = imread(input_path).astype(np.uint8)
        resolution = np.ones(3, dtype=float)

    if volume.ndim != 3:
        raise ValueError(
            f"Expected a 3D centreline volume, received an array with {volume.ndim} dimensions."
        )

    return volume, resolution


@njit(parallel=True, cache=True)
def _binarize_and_bound_3d(volume: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mins = np.array(volume.shape, dtype=np.int_)
    maxes = np.zeros(3, dtype=np.int_)

    for z in prange(volume.shape[0]):
        for y in range(volume.shape[1]):
            for x in range(volume.shape[2]):
                point = volume[z, y, x]
                if point:
                    volume[z, y, x] = 1
                    if z < mins[0]:
                        mins[0] = z
                    elif z > maxes[0]:
                        maxes[0] = z
                    if y < mins[1]:
                        mins[1] = y
                    elif y > maxes[1]:
                        maxes[1] = y
                    if x < mins[2]:
                        mins[2] = x
                    elif x > maxes[2]:
                        maxes[2] = x

    bounded = volume[
        mins[0] : maxes[0] + 1,
        mins[1] : maxes[1] + 1,
        mins[2] : maxes[2] + 1,
    ]
    return bounded, mins


def _prepare_volume(volume: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if not np.any(volume):
        raise ValueError("Input volume does not contain any non-zero centreline voxels.")

    volume = np.asarray(volume, dtype=np.uint8)
    if not volume.data.contiguous:
        volume = np.ascontiguousarray(volume)

    volume, minima = _binarize_and_bound_3d(volume)
    volume = np.pad(volume, 1)
    return volume, minima


def _find_centerlines(volume: np.ndarray) -> np.ndarray:
    points = np.vstack(np.nonzero(volume)).T
    return points.astype(np.int_)


def _absolute_points(points: np.ndarray, minima: np.ndarray) -> np.ndarray:
    return (points + minima).astype(np.int_)


def _orientations() -> np.ndarray:
    scan = np.array(
        [
            [2, 2, 0],
            [2, 2, 1],
            [2, 2, 2],
            [1, 2, 0],
            [1, 2, 1],
            [1, 2, 2],
            [2, 1, 0],
            [2, 1, 1],
            [2, 1, 2],
            [1, 1, 2],
            [2, 0, 0],
            [2, 0, 1],
            [2, 0, 2],
        ]
    )
    scan -= 1
    return scan


def _construct_vertex_lut(points: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    values = np.arange(points.shape[0])
    vertex_lut = np.zeros(shape, dtype=np.int_)
    vertex_lut[points[:, 0], points[:, 1], points[:, 2]] = values
    return vertex_lut


@njit(cache=True)
def _identify_edges(
    points: np.ndarray, vertex_lut: np.ndarray, spaces: np.ndarray
) -> list[tuple[int, int]]:
    edges = []

    for i in range(points.shape[0]):
        local = spaces + points[i]

        for j in range(local.shape[0]):
            target_index = vertex_lut[local[j, 0], local[j, 1], local[j, 2]]
            if target_index > 0:
                edges.append((i, target_index))

    return edges


def _restore_external_neighbors(g: ig.Graph, clique_subgraph_vs: ig.VertexSeq) -> list[int]:
    g_vs = g.vs[clique_subgraph_vs["id"]]

    neighbors = []
    for g_v, gb_v in zip(g_vs, clique_subgraph_vs):
        if g_v.degree() != gb_v.degree():
            clique_neighbors = [n["id"] for n in gb_v.neighbors()]
            neighbors.extend(
                n["id"] for n in g_v.neighbors() if n["id"] not in clique_neighbors
            )

    return neighbors


def _new_vertex(
    g: ig.Graph, vs: ig.VertexSeq, coords: np.ndarray | None = None
) -> tuple[tuple[float, float, np.ndarray], list[int]]:
    vis_radius = float(np.mean(vs["vis_radius"]))
    v_radius = float(np.mean(vs["v_radius"]))

    if coords is None:
        coords = np.mean(vs["v_coords"], axis=0)

    neighbors = _restore_external_neighbors(g, vs)
    return (v_radius, vis_radius, coords), neighbors


def _branch_graph(
    g: ig.Graph, components: bool = False
) -> tuple[ig.Graph, list[list[int]]]:
    g.vs["id"] = np.arange(g.vcount())
    gbs = g.subgraph(g.vs.select(_degree_gt=2))

    if components:
        cliques = [clique for clique in gbs.components() if len(clique) > 3]
    else:
        while True:
            count = len(gbs.vs.select(_degree_lt=2))
            if count == 0:
                break
            gbs = gbs.subgraph(gbs.vs.select(_degree_gt=1))
        cliques = [clique for clique in gbs.maximal_cliques() if 2 < len(clique) < 5]

    return gbs, cliques


def _class1_processing(g: ig.Graph, gbs: ig.Graph, cliques: list[list[int]]) -> int:
    edges_togo = []

    for clique in cliques:
        g_vs = g.vs[gbs.vs[clique]["id"]]
        if any(degree >= 5 for degree in g_vs.degree()):
            continue

        weights = list(g_vs["v_radius"])
        for i, v in enumerate(g_vs):
            for neighbor in v.neighbors():
                weights[i] += neighbor["v_radius"]

        sorted_ids = [vertex for _, vertex in sorted(zip(weights, g_vs))]
        edges_togo.append((sorted_ids[0]["id"], sorted_ids[1]["id"]))

    if edges_togo:
        g.delete_edges(edges_togo)

    return len(edges_togo)


def _class2_filter(
    g: ig.Graph, gbs: ig.Graph, clique: list[int]
) -> list[tuple[float, float, np.ndarray] | list[int]]:
    gb_vs = gbs.vs[clique]
    vertex, neighbors = _new_vertex(g, gb_vs)
    return [vertex, neighbors]


def _class3_filter(
    g: ig.Graph, gbs: ig.Graph, clique: list[int]
) -> list[list[tuple[float, float, np.ndarray] | list[int]]]:
    vs = gbs.vs[clique]
    coords = np.insert(np.array(vs["v_coords"]), 3, np.arange(len(clique)), axis=1)

    distances_rough = [0, 0, 0]
    for i in range(3):
        coords = coords[np.argsort(coords[:, i])]
        distances_rough[i] = np.abs(coords[0, :3] - coords[-1, :3]).sum()
    axis = int(np.argmax(distances_rough))
    coords = coords[np.argsort(coords[:, axis])]

    slices = np.linspace(0, coords.shape[0], min(6, coords.shape[0]), endpoint=True)

    new_vertices = []
    for i in range(slices.shape[0] - 1):
        bottom, top = int(slices[i]), int(slices[i + 1])
        ids = coords[bottom:top, 3].tolist()
        vertex, neighbors = _new_vertex(g, vs[ids])
        new_vertices.append([vertex, neighbors])

    return new_vertices


def _class2and3_processing(g: ig.Graph, gbs: ig.Graph, cliques: list[list[int]]) -> tuple[int, int]:
    new_edges = []
    vertices_togo = []
    class_two = []
    class_three = []

    for clique in cliques:
        vertices_togo.extend(gbs.vs[clique]["id"])
        if len(clique) <= 50:
            class_two.append(_class2_filter(g, gbs, clique))
        else:
            class_three.append(_class3_filter(g, gbs, clique))

    for cluster in class_two:
        v_info = cluster[0]
        neighbors = cluster[1]
        v = g.add_vertex(v_radius=v_info[0], vis_radius=v_info[1], v_coords=v_info[2])
        new_edges.extend(sorted((v.index, n)) for n in neighbors)

    for cluster in class_three:
        cluster_line = []
        for c in cluster:
            v_info = c[0]
            neighbors = c[1]
            v = g.add_vertex(
                v_radius=v_info[0], vis_radius=v_info[1], v_coords=v_info[2]
            )
            new_edges.extend(sorted((v.index, n)) for n in neighbors)

        for i in range(len(cluster_line) - 1):
            new_edges.append(sorted((cluster_line[i], cluster_line[i + 1])))

    new_edges = [tuple(edge) for edge in {tuple(edge) for edge in new_edges}]
    if new_edges:
        g.add_edges(new_edges)
    if vertices_togo:
        g.delete_vertices(vertices_togo)

    return len(class_two), len(class_three)


def clique_filter(g: ig.Graph, verbose: bool = False) -> None:
    if verbose:
        tic = pf()

    processed = 0
    gbs, cliques = _branch_graph(g)

    processed += _class1_processing(g, gbs, cliques)
    gbs, cliques = _branch_graph(g, components=True)

    if cliques:
        class_two, class_three = _class2and3_processing(g, gbs, cliques)
        processed += class_two + class_three

    del g.vs["id"]

    if verbose:
        _log(
            f"{processed} branch point clique clusters corrected in {pf() - tic:0.2f} seconds.",
            verbose,
        )


def _seg_interpolate(point_coords: np.ndarray, vis_radius: float) -> np.ndarray:
    num_verts = point_coords.shape[0]
    spline_degree = 3 if num_verts > 4 else max(1, num_verts - 1)
    knots = knotvector.generate(spline_degree, num_verts)
    tck = [
        knots,
        [point_coords[:, 0], point_coords[:, 1], point_coords[:, 2]],
        spline_degree,
    ]

    delta = max(3, ceil(num_verts / log(num_verts, 2)))
    if num_verts > 100 or (vis_radius > 3 and num_verts > 20):
        delta = int(delta / 2)

    u = np.linspace(0, 1, delta, endpoint=True)
    return np.array(interpolate.splev(u, tck)).T


@njit(fastmath=True, cache=True)
def _length_calc(coords: np.ndarray, resolution: np.ndarray) -> float:
    deltas = coords[0:-1] - coords[1:]
    squares = (deltas * resolution) ** 2
    return np.sum(np.sqrt(np.sum(squares, axis=1)))


def _feature_length(
    g: ig.Graph,
    point_list: list[int],
    resolution: np.ndarray,
    centerline_smoothing: bool,
) -> float:
    coords = np.array(g.vs[point_list]["v_coords"])
    if centerline_smoothing:
        mean_radius = float(np.mean(g.vs[point_list]["v_radius"]))
        coords = _seg_interpolate(coords, mean_radius / np.min(resolution))
    return float(_length_calc(coords, resolution))


def _small_seg_path_length(
    g: ig.Graph,
    segment: list[int],
    segment_ids: ig.VertexSeq,
    resolution: np.ndarray,
    centerline_smoothing: bool,
) -> float:
    vert = segment_ids[segment[0]].index
    point_list = g.neighbors(vert)
    point_list.insert(1, vert)
    return _feature_length(g, point_list, resolution, centerline_smoothing)


def _loop_path(
    gsegs: ig.Graph, segment: list[int], segment_ids: ig.VertexSeq | None = None
) -> list[int]:
    try:
        loop = []
        v1 = segment[0]
        loop.append(v1)
        previous = v1
        looped = False
        i = 0
        size = len(segment)

        while not looped:
            if i > size:
                looped = True
                break
            neighbors = gsegs.neighbors(loop[-1])
            if neighbors[0] != previous and neighbors[0] != v1:
                loop.append(neighbors[0])
            elif neighbors[1] != previous and neighbors[1] != v1:
                loop.append(neighbors[1])
            else:
                looped = True
            previous = loop[-2]
            i += 1

        if segment_ids is not None:
            return [segment_ids[point].index for point in loop]
        return loop
    except Exception:
        if segment_ids is None:
            return segment[:2]
        return [segment_ids[v].index for v in segment[:2]]


def _large_seg_path_length(
    g: ig.Graph,
    gsegs: ig.Graph,
    segment: list[int],
    segment_ids: ig.VertexSeq,
    resolution: np.ndarray,
    centerline_smoothing: bool,
) -> float:
    degrees = gsegs.degree(segment)
    endpoints = [segment[i] for i, degree in enumerate(degrees) if degree == 1]

    if len(endpoints) == 2:
        path = gsegs.get_shortest_paths(endpoints[0], to=endpoints[1], output="vpath")[0]
        point_list = [segment_ids[point].index for point in path]

        end_neighborhood = point_list[0:2] + point_list[-2:]
        for i in range(2):
            for neighbor in g.neighbors(point_list[-i]):
                if neighbor not in end_neighborhood:
                    if i == 0:
                        point_list.insert(0, neighbor)
                    else:
                        point_list.append(neighbor)
    else:
        point_list = _loop_path(gsegs, segment, segment_ids)

    return _feature_length(g, point_list, resolution, centerline_smoothing)


def _large_seg_filter_length(
    g: ig.Graph,
    segment: list[int],
    resolution: np.ndarray,
    centerline_smoothing: bool,
) -> float:
    degrees = g.degree(segment)
    endpoints = [segment[i] for i, degree in enumerate(degrees) if degree == 1]

    if len(endpoints) == 2:
        point_list = g.get_shortest_paths(endpoints[0], to=endpoints[1], output="vpath")[0]
    else:
        point_list = _loop_path(g, segment)

    return _feature_length(g, point_list, resolution, centerline_smoothing)


def prune_graph(
    g: ig.Graph,
    prune_length: float,
    resolution: np.ndarray,
    centerline_smoothing: bool = True,
    verbose: bool = False,
) -> None:
    if prune_length <= 0:
        return

    if verbose:
        tic = pf()

    pruned_total = 0
    prune_limit = prune_length

    for pass_index in range(2):
        segment_ids = g.vs.select(_degree_lt=3)
        gsegs = g.subgraph(segment_ids)
        segments = [segment for segment in gsegs.components() if len(segment) < max(1, prune_limit)]

        vertices_togo = []
        pruned_pass = 0
        for segment in segments:
            if len(segment) >= prune_limit:
                continue

            vertices = [segment_ids[vertex].index for vertex in segment]
            degrees = g.degree(vertices)
            if degrees.count(1) != 1:
                continue

            if len(segment) == 1:
                segment_length = _small_seg_path_length(
                    g, segment, segment_ids, resolution, centerline_smoothing
                )
            else:
                segment_length = _large_seg_path_length(
                    g, gsegs, segment, segment_ids, resolution, centerline_smoothing
                )

            if segment_length < prune_limit:
                pruned_pass += 1
                vertices_togo.extend(vertices)

        if vertices_togo:
            g.delete_vertices(vertices_togo)

        pruned_total += pruned_pass
        if pass_index == 0:
            prune_limit = 1.01

    if verbose:
        _log(f"Pruned {pruned_total} segments in {pf() - tic:0.2f} seconds.", verbose)


def filter_graph(
    g: ig.Graph,
    filter_length: float,
    resolution: np.ndarray,
    centerline_smoothing: bool = True,
    verbose: bool = False,
) -> None:
    if verbose:
        tic = pf()

    isolated = g.vs.select(_degree=0)
    if isolated:
        g.delete_vertices(isolated)

    filtered = 0
    if filter_length > 0:
        clusters = [cluster for cluster in g.components() if len(cluster) <= max(2, filter_length)]
        vertices_togo = []

        for cluster in clusters:
            degrees = g.degree(cluster)
            if degrees.count(1) != 2:
                continue

            if len(cluster) < 4:
                segment_length = _feature_length(
                    g, cluster, resolution, centerline_smoothing
                )
            else:
                segment_length = _large_seg_filter_length(
                    g, cluster, resolution, centerline_smoothing
                )

            if segment_length < filter_length:
                vertices_togo.extend(cluster)
                filtered += 1

        if vertices_togo:
            g.delete_vertices(vertices_togo)

    if verbose and filter_length > 0:
        _log(
            f"Filtered {filtered} isolated segments in {pf() - tic:0.2f} seconds.",
            verbose,
        )


def create_graph(
    volume_shape: tuple[int, int, int],
    points: np.ndarray,
    point_minima: np.ndarray,
) -> ig.Graph:
    g = ig.Graph()
    g.add_vertices(len(points))
    g.vs["v_coords"] = _absolute_points(points, point_minima)
    g.vs["v_radius"] = np.ones(len(points), dtype=float)
    g.vs["vis_radius"] = np.ones(len(points), dtype=float)

    spaces = _orientations()
    vertex_lut = _construct_vertex_lut(points, volume_shape)
    edges = _identify_edges(points, vertex_lut, spaces)
    g.add_edges(edges)
    return g


def save_graphml_graph(g: ig.Graph, output_path: str) -> None:
    graph = g.copy()

    if graph.vcount() == 0:
        raise ValueError("Graph is empty after cleanup; no GraphML file was written.")

    points = np.array(graph.vs["v_coords"])
    graph.vs["X"] = points[:, 2]
    graph.vs["Y"] = points[:, 1]
    graph.vs["Z"] = points[:, 0]
    del graph.vs["v_coords"]

    output_dir = os.path.dirname(os.path.abspath(output_path))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    graph.write(output_path)


def skel_to_graph(
    input_path: str,
    output_path: str,
    prune_length: float,
    filter_length: float,
    verbose: bool = False,
) -> ig.Graph:
    start = pf()
    _log(f"Loading centreline volume: {input_path}", verbose)
    volume, resolution = _load_volume(input_path)
    volume, point_minima = _prepare_volume(volume)

    points = _find_centerlines(volume)
    _log(f"Found {len(points)} centreline voxels.", verbose)

    _log("Creating raw voxel graph...", verbose)
    graph = create_graph(volume.shape, points, point_minima)

    _log("Running clique filtering...", verbose)
    clique_filter(graph, verbose=verbose)

    _log("Pruning endpoint branches...", verbose)
    prune_graph(
        graph,
        prune_length=prune_length,
        resolution=resolution,
        centerline_smoothing=True,
        verbose=verbose,
    )

    _log("Filtering isolated components...", verbose)
    filter_graph(
        graph,
        filter_length=filter_length,
        resolution=resolution,
        centerline_smoothing=True,
        verbose=verbose,
    )

    _log(f"Saving GraphML: {output_path}", verbose)
    save_graphml_graph(graph, output_path)

    _log(f"Completed in {pf() - start:0.2f} seconds.", verbose)
    return graph


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a 3D centreline volume into a cleaned GraphML voxel graph."
    )
    parser.add_argument("input_path", help="Path to the input 3D centreline volume.")
    parser.add_argument("output_path", help="Path to the output GraphML file.")
    parser.add_argument(
        "--prune-length",
        type=float,
        default=0.0,
        help="Endpoint branch length threshold used for pruning.",
    )
    parser.add_argument(
        "--filter-length",
        type=float,
        default=0.0,
        help="Isolated component length threshold used for filtering.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress messages while running the pipeline.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    skel_to_graph(
        input_path=args.input_path,
        output_path=args.output_path,
        prune_length=args.prune_length,
        filter_length=args.filter_length,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
