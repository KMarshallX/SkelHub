"""
Standalone centerline-volume to GraphML pipeline.

This script extracts the voxel-graph construction and cleanup path from
VesselVio without pulling in the feature-analysis/reporting pipeline.
"""
from __future__ import annotations

'''bash
Usage:

python graph_generation.py input_centerline.nii output_graph.graphml \
        --prune-length 5 \
        --filter-length 5 \
        --verbose
'''



import argparse
import os
from math import ceil, log
from pathlib import Path
from time import perf_counter as pf

import igraph as ig
import nibabel
import numpy as np
from geomdl import knotvector
from numba import njit
from scipy import interpolate
from skimage.io import imread


########################
### Volume Utilities ###
########################
def load_nii_volume(file_path: str) -> np.ndarray:
    proxy = nibabel.load(file_path)
    data = proxy.dataobj.get_unscaled().transpose()
    if data.ndim == 4:
        data = data[0]
    return data


def load_volume(file_path: str, verbose: bool = False) -> tuple[np.ndarray | None, tuple[int, ...] | None]:
    tic = pf()

    if Path(file_path).suffix.lower() == ".nii":
        try:
            volume = load_nii_volume(file_path)
        except Exception as error:
            print(f"Could not load .nii file using nibabel: {error}")
            volume = skimage_load(file_path)
    else:
        volume = skimage_load(file_path)

    if volume is None or volume.ndim not in (2, 3):
        return None, None

    if verbose:
        print(f"Volume loaded in {pf() - tic:.2f} s.")

    return volume, volume.shape


def skimage_load(file_path: str) -> np.ndarray | None:
    try:
        return imread(file_path).astype(np.uint8)
    except Exception as error:
        print(f"Unable to read image file using skimage.io.imread: {error}")
        return None


def binary_check(volume: np.ndarray) -> bool:
    middle = int(volume.shape[0] / 2)
    unique = np.unique(volume[middle])
    return unique.shape[0] < 3


def volume_prep(volume: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    volume = np.asarray(volume, dtype=np.uint8)
    if not volume.data.contiguous:
        volume = np.ascontiguousarray(volume)

    if volume.ndim != 3:
        raise ValueError("graph_generation.py currently expects a 3D centerline volume.")

    return binarize_and_bound_3d(volume)


@njit(parallel=True, nogil=True, cache=True)
def binarize_and_bound_3d(volume: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mins = np.array(volume.shape, dtype=np.int_)
    maxes = np.zeros(3, dtype=np.int_)
    for z in range(volume.shape[0]):
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

    volume = volume[
        mins[0] : maxes[0] + 1,
        mins[1] : maxes[1] + 1,
        mins[2] : maxes[2] + 1,
    ]
    return volume, mins


def pad_volume(volume: np.ndarray) -> np.ndarray:
    return np.pad(volume, 1)


def absolute_points(points: np.ndarray, minima: np.ndarray) -> np.ndarray:
    return (points + minima).astype(np.int_)


@njit(cache=True)
def find_centerlines(centerline_volume: np.ndarray) -> np.ndarray:
    points = np.vstack(np.nonzero(centerline_volume)).T
    return points.astype(np.int_)


########################
### Graph Creation   ###
########################
def orientations() -> np.ndarray:
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
    return scan - 1


def construct_vlut(points: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    values = np.arange(points.shape[0])
    vertex_lut = np.zeros(shape, dtype=np.int_)
    vertex_lut[points[:, 0], points[:, 1], points[:, 2]] = values
    return vertex_lut


@njit(cache=True)
def identify_edges(points: np.ndarray, vertex_lut: np.ndarray, spaces: np.ndarray) -> list[tuple[int, int]]:
    edges = []
    for i in range(points.shape[0]):
        local = spaces + points[i]
        for j in range(local.shape[0]):
            target_index = vertex_lut[local[j, 0], local[j, 1], local[j, 2]]
            if target_index > 0:
                edges.append((i, target_index))
    return edges


def create_graph(volume_shape, points, point_minima, verbose=False):
    if verbose:
        print("Creating graph...", end="\r")
        tic = pf()

    graph = ig.Graph()
    graph.add_vertices(len(points))
    graph.vs["v_coords"] = absolute_points(points, point_minima)

    # Placeholder values keep clique/pruning/filter semantics intact without
    # running VesselVio's radius-estimation pipeline.
    graph.vs["v_radius"] = np.ones(len(points), dtype=float)
    graph.vs["vis_radius"] = np.zeros(len(points), dtype=float)

    vertex_lut = construct_vlut(points, volume_shape)
    graph.add_edges(identify_edges(points, vertex_lut, orientations()))

    clique_filter_input(graph, verbose=verbose)

    if verbose:
        print(f"Graph creation completed in {pf() - tic:0.2f} seconds.")

    return graph


########################
### Clique Filtering ###
########################
def g_branch_graph(graph, components=False):
    graph.vs["id"] = np.arange(graph.vcount())
    branch_subgraph = graph.subgraph(graph.vs.select(_degree_gt=2))

    if components:
        cliques = [clique for clique in branch_subgraph.components() if len(clique) > 3]
    else:
        while True:
            count = len(branch_subgraph.vs.select(_degree_lt=2))
            if count == 0:
                break
            branch_subgraph = branch_subgraph.subgraph(branch_subgraph.vs.select(_degree_gt=1))
        cliques = [clique for clique in branch_subgraph.maximal_cliques() if 2 < len(clique) < 5]

    return branch_subgraph, cliques


def restore_v_neighbors(graph, gb_vs):
    graph_vs = graph.vs[gb_vs["id"]]

    neighbors = []
    for graph_v, gb_v in zip(graph_vs, gb_vs):
        if graph_v.degree() != gb_v.degree():
            clique_neighbors = [n["id"] for n in gb_v.neighbors()]
            neighbors += [n["id"] for n in graph_v.neighbors() if n["id"] not in clique_neighbors]

    return neighbors


def new_vertex(graph, vs, coords=None):
    vis_radius = float(np.mean(vs["vis_radius"])) if vs[0]["vis_radius"] else None
    v_radius = float(np.mean(vs["v_radius"]))
    if coords is None:
        coords = np.mean(vs["v_coords"], axis=0)
    vertex = (v_radius, vis_radius, coords)
    neighbors = restore_v_neighbors(graph, vs)
    return vertex, neighbors


def class3_filter(graph, branch_subgraph, clique):
    vs = branch_subgraph.vs[clique]
    coords = np.insert(np.array(vs["v_coords"]), 3, np.arange(len(clique)), axis=1)

    distances_rough = [0, 0, 0]
    for i in range(3):
        coords = coords[np.argsort(coords[:, i])]
        distances_rough[i] = np.abs(coords[0, :3] - coords[-1, :3]).sum()
    axis = np.argmax(distances_rough)
    coords = coords[np.argsort(coords[:, axis])]

    slices = np.linspace(0, coords.shape[0], min(6, coords.shape[0]), endpoint=True)

    new_vertices = []
    for i in range(slices.shape[0] - 1):
        bottom, top = int(slices[i]), int(slices[i + 1])
        ids = coords[bottom:top, 3].tolist()
        vertex, neighbors = new_vertex(graph, vs[ids])
        new_vertices.append([vertex, neighbors])

    return new_vertices


def class2_filter(graph, branch_subgraph, clique):
    gb_vs = branch_subgraph.vs[clique]
    return list(new_vertex(graph, gb_vs))


def class1_filter(graph, branch_subgraph, cliques):
    edges_togo = []
    for clique in cliques:
        graph_vs = graph.vs[branch_subgraph.vs[clique]["id"]]
        if any(degree >= 5 for degree in graph_vs.degree()):
            continue

        weights = list(graph_vs["v_radius"])
        for i, vertex in enumerate(graph_vs):
            for neighbor in vertex.neighbors():
                weights[i] += neighbor["v_radius"]

        sorted_ids = [idx for _, idx in sorted(zip(weights, graph_vs))]
        edges_togo.append((sorted_ids[0]["id"], sorted_ids[1]["id"]))

    return edges_togo


def class2and3_processing(graph, branch_subgraph, cliques):
    new_edges = []
    vertices_togo = []
    class_two = []
    class_three = []

    for clique in cliques:
        vertices_togo += branch_subgraph.vs[clique]["id"]
        if len(clique) <= 50:
            class_two.append(class2_filter(graph, branch_subgraph, clique))
        else:
            class_three.append(class3_filter(graph, branch_subgraph, clique))

    for cluster in class_two:
        v_info, neighbors = cluster
        vertex = graph.add_vertex(v_radius=v_info[0], vis_radius=v_info[1], v_coords=v_info[2])
        new_edges.extend(sorted(tuple([vertex.index, n]) for n in neighbors))

    for cluster in class_three:
        cluster_line = []
        for entry in cluster:
            v_info, neighbors = entry
            vertex = graph.add_vertex(v_radius=v_info[0], vis_radius=v_info[1], v_coords=v_info[2])
            new_edges.extend(sorted(tuple([vertex.index, n]) for n in neighbors))
            # Preserve intended centerline chaining semantics for class-3 replacements.
            cluster_line.append(vertex.index)

        for i in range(len(cluster_line) - 1):
            edge = tuple(sorted((cluster_line[i], cluster_line[i + 1])))
            new_edges.append(edge)

    graph.add_edges(list(set(new_edges)))
    graph.delete_vertices(vertices_togo)
    return len(class_two), len(class_three)


def clique_filter_input(graph, verbose=False):
    if verbose:
        tic = pf()
        print("Filtering cliques...", end="\r")

    processed = 0
    branch_subgraph, cliques = g_branch_graph(graph)

    class_one_edges = class1_filter(graph, branch_subgraph, cliques)
    class_one = len(class_one_edges)
    graph.delete_edges(class_one_edges)
    processed += class_one

    branch_subgraph, cliques = g_branch_graph(graph, components=True)
    class_two = class_three = 0
    if cliques:
        class_two, class_three = class2and3_processing(graph, branch_subgraph, cliques)
        processed += class_two + class_three

    del graph.vs["id"]

    if verbose:
        print(f"{processed} branch point clique clusters corrected in {pf() - tic:0.2f} seconds.")


#############################
### Path Length Geometry  ###
#############################
def delta_calc(num_verts, vis_radius):
    delta = max(3, ceil(num_verts / log(num_verts, 2)))
    if num_verts > 100 or (vis_radius > 3 and num_verts > 20):
        delta = int(delta / 2)
    return delta


def seg_interpolate(point_coords, vis_radius):
    num_verts = point_coords.shape[0]
    spline_degree = 3 if num_verts > 4 else max(1, num_verts - 1)

    knots = knotvector.generate(spline_degree, num_verts)
    tck = [knots, [point_coords[:, 0], point_coords[:, 1], point_coords[:, 2]], spline_degree]

    delta = delta_calc(num_verts, vis_radius)
    u = np.linspace(0, 1, delta, endpoint=True)

    return np.array(interpolate.splev(u, tck)).T


@njit(fastmath=True, cache=True)
def length_calc(coords, resolution):
    deltas = coords[0:-1] - coords[1:]
    squares = (deltas * resolution) ** 2
    results = np.sqrt(np.sum(squares, axis=1))
    return np.sum(results)


def feature_length(graph, point_list, resolution, centerline_smoothing=True):
    point_coords = np.array(graph.vs[point_list]["v_coords"])
    if centerline_smoothing and point_coords.shape[0] > 2:
        point_coords = seg_interpolate(point_coords, np.mean(graph.vs[point_list]["v_radius"]))
    return float(length_calc(point_coords, resolution))


def loop_path(graph, segment, segment_ids=None):
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

            neighbors = graph.neighbors(loop[-1])
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
        if segment_ids is not None:
            return [segment_ids[v].index for v in segment[0:2]]
        return list(segment[0:2])


def small_seg_path(graph, segment, segment_ids, resolution, centerline_smoothing=True):
    vert = segment_ids[segment[0]].index
    point_list = graph.neighbors(vert)
    point_list.insert(1, vert)
    return feature_length(graph, point_list, resolution, centerline_smoothing=centerline_smoothing)


def large_seg_path(graph, gsegs, segment, segment_ids, resolution, centerline_smoothing=True):
    degrees = gsegs.degree(segment)
    endpoints = [segment[i] for i, degree in enumerate(degrees) if degree == 1]

    if len(endpoints) == 2:
        path = gsegs.get_shortest_paths(endpoints[0], to=endpoints[1], output="vpath")[0]
        point_list = [segment_ids[point].index for point in path]

        end_neighborhood = point_list[0:2] + point_list[-2:]
        for i in range(2):
            for neighbor in graph.neighbors(point_list[-i]):
                if neighbor not in end_neighborhood:
                    if i == 0:
                        point_list.insert(0, neighbor)
                    else:
                        point_list.append(neighbor)
    else:
        point_list = loop_path(gsegs, segment, segment_ids)

    return feature_length(graph, point_list, resolution, centerline_smoothing=centerline_smoothing)


def large_seg_filter(graph, segment, resolution, centerline_smoothing=True):
    degrees = graph.degree(segment)
    endpoints = [segment[loc] for loc, degree in enumerate(degrees) if degree == 1]

    if len(endpoints) == 2:
        point_list = graph.get_shortest_paths(endpoints[0], to=endpoints[1], output="vpath")[0]
    else:
        point_list = loop_path(graph, segment)

    return feature_length(graph, point_list, resolution, centerline_smoothing=centerline_smoothing)


############################
### Pruning / Filtering  ###
############################
def segment_isolation(graph, degree_filter, prune_length):
    segment_ids = graph.vs.select(_degree_lt=degree_filter)
    gsegs = graph.subgraph(segment_ids)
    segments = [segment for segment in gsegs.clusters() if len(segment) < max(1, prune_length)]
    return gsegs, segments, segment_ids


def prune_input(graph, prune_length, resolution, centerline_smoothing=True, verbose=False):
    if verbose:
        tic = pf()
        print("Pruning endpoint segments...", end="\r")

    gsegs, segments, segment_ids = segment_isolation(graph, 3, prune_length)
    vertices_togo = []
    pruned = 0

    for segment in segments:
        num_verts = len(segment)
        if num_verts >= prune_length:
            continue

        vertices = [segment_ids[vertex].index for vertex in segment]
        degrees = graph.degree(vertices)
        if degrees.count(1) != 1:
            continue

        if num_verts == 1:
            segment_length = small_seg_path(
                graph,
                segment,
                segment_ids,
                resolution,
                centerline_smoothing=centerline_smoothing,
            )
        else:
            segment_length = large_seg_path(
                graph,
                gsegs,
                segment,
                segment_ids,
                resolution,
                centerline_smoothing=centerline_smoothing,
            )

        if segment_length < prune_length:
            pruned += 1
            vertices_togo.extend(vertices)

    graph.delete_vertices(vertices_togo)

    # Match VesselVio's second-pass cleanup for single-voxel stubs.
    gsegs, segments, segment_ids = segment_isolation(graph, 3, 1.01)
    vertices_togo = []
    for segment in segments:
        if len(segment) != 1:
            continue
        vertices = [segment_ids[vertex].index for vertex in segment]
        if graph.degree(vertices).count(1) != 1:
            continue
        segment_length = small_seg_path(
            graph,
            segment,
            segment_ids,
            resolution,
            centerline_smoothing=centerline_smoothing,
        )
        if segment_length < 1.01:
            pruned += 1
            vertices_togo.extend(vertices)

    graph.delete_vertices(vertices_togo)

    if verbose:
        print(f"Pruned {pruned} segments in {pf() - tic:0.2f} seconds.")


def filter_input(graph, filter_length, resolution, centerline_smoothing=True, verbose=False):
    if verbose:
        tic = pf()
        print("Filtering isolated segments...", end="\r")

    graph.delete_vertices(graph.vs.select(_degree=0))

    filtered = 0
    if filter_length > 0:
        clusters = [cluster for cluster in graph.components() if len(cluster) <= max(2, filter_length)]
        vertices_togo = []

        for cluster in clusters:
            degrees = graph.degree(cluster)
            if degrees.count(1) != 2:
                continue

            if len(cluster) < 4:
                segment_length = feature_length(
                    graph,
                    cluster,
                    resolution,
                    centerline_smoothing=centerline_smoothing,
                )
            else:
                segment_length = large_seg_filter(
                    graph,
                    cluster,
                    resolution,
                    centerline_smoothing=centerline_smoothing,
                )

            if segment_length < filter_length:
                vertices_togo.extend(cluster)
                filtered += 1

        graph.delete_vertices(vertices_togo)

    if verbose:
        if filter_length > 0:
            print(f"Filtered {filtered} isolated segments in {pf() - tic:0.2f} seconds.")
        else:
            print("", end="\r")


########################
### GraphML Export   ###
########################
def save_graphml(graph: ig.Graph, output_path: str, verbose: bool = False) -> None:
    if verbose:
        print("Saving GraphML...", end="\r")

    if graph.vcount() == 0:
        raise ValueError("The cleaned graph is empty; no GraphML file was written.")

    graph = graph.copy()
    points = np.array(graph.vs["v_coords"])
    graph.vs["X"] = points[:, 2]
    graph.vs["Y"] = points[:, 1]
    graph.vs["Z"] = points[:, 0]
    del graph.vs["v_coords"]

    output_dir = os.path.dirname(os.path.abspath(output_path))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    graph.write(output_path)


########################
### Public API / CLI ###
########################
def generate_graph(
    input_path: str,
    output_path: str,
    prune_length: float = 0.0,
    filter_length: float = 0.0,
    verbose: bool = False,
) -> ig.Graph:
    resolution = np.ones(3, dtype=float)

    volume, _ = load_volume(input_path, verbose=verbose)
    if volume is None:
        raise ValueError(f"Unable to load volume from {input_path!r}.")
    if volume.ndim != 3:
        raise ValueError("Only 3D centerline volumes are supported.")
    if not np.any(volume):
        raise ValueError("Input volume is empty.")
    if not binary_check(volume):
        raise ValueError("Input must be binary or binary-like.")

    volume, point_minima = volume_prep(volume)
    volume = pad_volume(volume)
    points = find_centerlines(volume)
    if points.shape[0] == 0:
        raise ValueError("No centerline voxels were found in the input volume.")

    graph = create_graph(volume.shape, points, point_minima, verbose=verbose)

    if prune_length > 0:
        prune_input(graph, prune_length, resolution, centerline_smoothing=True, verbose=verbose)

    filter_input(graph, filter_length, resolution, centerline_smoothing=True, verbose=verbose)
    save_graphml(graph, output_path, verbose=verbose)
    return graph


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a cleaned voxel graph from a 3D centerline volume and save it as GraphML."
    )
    parser.add_argument("input_path", help="Path to the input 3D centerline volume.")
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
        help="Print progress information.",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    generate_graph(
        input_path=args.input_path,
        output_path=args.output_path,
        prune_length=args.prune_length,
        filter_length=args.filter_length,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
