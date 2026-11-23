"""Foreground-guided graph refinement with fixed 26/6 digital topology.

Sequential simple-point deletion preserves the foreground's topology. The
26-neighbour graph of the surviving voxels still has filled triangles; removing
those relations over GF(2) leaves exactly the foreground's independent tunnels,
with their correspondence to the mask intact (not just the same cycle count).

Simple-point criterion: Bertrand's T26(foreground) = T6(background) = 1;
T6 counts components in N18 that touch a face neighbour of the deleted voxel.
See https://www.dgtal.org/doc/2.0/moduleDigitalTopology.html.
"""

import heapq
from itertools import product

import numpy as np
from scipy import ndimage, sparse
from scipy.spatial import cKDTree

from .contraction import laplacian_graph_contraction
from .graph import compute_sparse_adjacency_matrix
from .objects import UnionFind
from .utils import (
    _edge_voxels,
    _nonincident_intersection_pairs,
    _nonincident_intersections,
)


_FOREGROUND = ndimage.generate_binary_structure(3, 3)
_BACKGROUND = ndimage.generate_binary_structure(3, 1)
_N18 = ndimage.generate_binary_structure(3, 2)
_FACES = _BACKGROUND.copy()
_FACES[1, 1, 1] = False
_OFFSETS = np.array([p for p in product((-1, 0, 1), repeat=3) if p != (0, 0, 0)])


def foreground_topology(mask):
    """Return component, tunnel and cavity counts for closed foreground cubes."""
    mask = np.asarray(mask, dtype=bool)
    coordinates = np.argwhere(mask)
    components = ndimage.label(mask, _FOREGROUND)[1]
    cavities = ndimage.label(~np.pad(mask, 1), _BACKGROUND)[1] - 1
    if not len(coordinates):
        return 0, 0, 0

    def count_cells(offsets):
        points = np.concatenate([coordinates + offset for offset in offsets])
        return len(np.unique(points, axis=0))

    vertices = count_cells(list(product((0, 1), repeat=3)))
    edges = faces = 0
    for axis in range(3):
        # An edge varies along one axis; a face is perpendicular to one axis.
        edges += count_cells([p for p in product((0, 1), repeat=3) if p[axis] == 0])
        offset = np.zeros(3, dtype=int)
        offset[axis] = 1
        faces += count_cells([np.zeros(3, dtype=int), offset])
    euler = vertices - edges + faces - len(coordinates)
    return components, components + cavities - euler, cavities


def _is_simple(neighbourhood):
    """Test one deletion against the current, rather than a cached, neighbourhood."""
    foreground = neighbourhood.copy()
    foreground[1, 1, 1] = False
    if ndimage.label(foreground, _FOREGROUND)[1] != 1:
        return False
    background = ~neighbourhood & _N18
    background[1, 1, 1] = False
    labels, _ = ndimage.label(background, _BACKGROUND)
    touching = np.unique(labels[_FACES])
    return np.count_nonzero(touching) == 1


def _thin_foreground(mask, guidance):
    """Peel simple voxels from the boundary inward, retaining curve endpoints."""
    work = np.pad(np.asarray(mask, dtype=bool), 1)
    coordinates = np.argwhere(work)
    distance = ndimage.distance_transform_edt(work)
    guide_distance = cKDTree(guidance).query(coordinates - 1)[0]
    priorities = {
        tuple(p): (float(distance[tuple(p)]), -float(np.round(d, 12)))
        for p, d in zip(coordinates, guide_distance)
    }
    queue = [(priorities[tuple(p)], tuple(p)) for p in coordinates]
    heapq.heapify(queue)
    queued = set(priorities)
    while queue:
        _, p = heapq.heappop(queue)
        queued.remove(p)
        if not work[p]:
            continue
        patch = work[tuple(slice(v - 1, v + 2) for v in p)]
        # A curve tip may be simple but deleting it shortens a branch.
        if np.count_nonzero(patch) <= 2 or not _is_simple(patch):
            continue
        work[p] = False
        for neighbour in np.asarray(p) + _OFFSETS:
            q = tuple(neighbour)
            if work[q] and q not in queued:
                heapq.heappush(queue, (priorities[q], q))
                queued.add(q)
    return np.argwhere(work) - 1


def _insert_binary_row(row, basis):
    """Insert an independent GF(2) row, represented by a Python integer."""
    while row:
        pivot = row.bit_length() - 1
        if pivot not in basis:
            basis[pivot] = row
            return True
        row ^= basis[pivot]
    return False


def _tunnel_graph(coordinates):
    """Keep a forest plus independent cycles modulo filled voxel triangles.

    Pairwise touching axis-aligned voxel cubes have a common intersection.
    Consequently their nerve is the clique complex of the 26-neighbour graph.
    Its triangle boundaries generate all relations needed for first homology.
    Projection onto non-forest edges gives coordinates for the graph cycle space.
    Choosing a basis modulo these boundaries preserves each tunnel class.
    """
    adjacency = compute_sparse_adjacency_matrix(cKDTree(coordinates), 26)
    rows, cols = sparse.triu(adjacency, k=1).nonzero()
    edges = sorted(
        zip(rows.tolist(), cols.tolist()),
        key=lambda e: (np.sum((coordinates[e[0]] - coordinates[e[1]]) ** 2), e),
    )
    forest = UnionFind(len(coordinates))
    kept = []
    chords = {}
    for edge in edges:
        if forest.union(*edge)[0]:
            kept.append(edge)
        else:
            chords[edge] = len(chords)
    neighbours = [
        set(adjacency.indices[adjacency.indptr[i] : adjacency.indptr[i + 1]])
        for i in range(len(coordinates))
    ]
    boundaries = {}
    for u, v in edges:
        for w in sorted(neighbours[u] & neighbours[v]):
            if w <= v:
                continue
            row = 0
            for edge in ((u, v), (u, w), (v, w)):
                if edge in chords:
                    row ^= 1 << chords[edge]
            _insert_binary_row(row, boundaries)
    tunnels = len(chords) - len(boundaries)
    for edge, index in chords.items():
        if _insert_binary_row(1 << index, boundaries):
            kept.append(edge)
    return np.asarray(kept, dtype=int).reshape(-1, 2), tunnels


def _edges_leaving_foreground(coordinates, edges, mask):
    """Flag edges whose straight segment leaves the closed foreground voxel cubes."""
    edges = np.asarray(edges, dtype=int).reshape(-1, 2)
    start, end = coordinates[edges[:, 0]], coordinates[edges[:, 1]]
    # Fast certificate: every voxel of the box covering the segment is foreground.
    lower = np.ceil(np.minimum(start, end) - 0.5 - 1e-10).astype(int)
    upper = np.floor(np.maximum(start, end) + 0.5 + 1e-10).astype(int)
    small = np.all(upper - lower <= 2, axis=1)
    certified = small & np.all(lower >= 0, axis=1) & np.all(
        upper < np.asarray(mask.shape), axis=1
    )
    for offset in product(range(3), repeat=3):
        voxel = lower + np.asarray(offset)
        inside_box = np.all(voxel <= upper, axis=1) & certified
        clipped = np.clip(voxel, 0, np.asarray(mask.shape) - 1)
        certified &= ~inside_box | mask[tuple(clipped.T)]
    leaving = np.zeros(len(edges), dtype=bool)
    for index in np.flatnonzero(~certified):
        try:
            _edge_voxels(start[index], end[index], mask.shape, mask)
        except ValueError:
            leaving[index] = True
    return leaving


_PIN_WEIGHT = 1e3
# Default retention weights of the second fit (--fit_w_H, --fit_w_H_medial), tuned on
# synthetic trees F01-F12 (odd cases for tuning, even cases held out) against the
# generating centreline; see
# tests/test_output/flow_fitting_20261106/run_20261106_161705/RESULTS.md. Contraction
# keeps its own w_H and medial boost; the other free flow settings are shared with it.
DEFAULT_FIT_W_H = 0.16
DEFAULT_FIT_W_H_MEDIAL = 3.0


def _repair_step(previous, proposed, edges, mask):
    """Return nodes to their previous positions until no edge leaves or crosses.

    Both ends of every offending edge go back, repeatedly. A valid previous state
    guarantees termination, since reverting everything restores it.
    """
    accepted = np.array(proposed, dtype=float)
    reverted = np.zeros(len(accepted), dtype=bool)
    check = np.arange(len(edges))
    while True:
        bad = check[_edges_leaving_foreground(accepted, edges[check], mask)]
        if not len(bad):
            crossing = {index for pair in _nonincident_intersection_pairs(
                accepted, edges, np.ones(3)) for index in pair}
            if not crossing:
                break
            bad = np.fromiter(crossing, dtype=int)
        nodes = np.unique(edges[bad])
        fresh = nodes[~reverted[nodes]]
        if not len(fresh):
            raise RuntimeError('Flow fitting could not restore a valid step.')
        accepted[fresh] = previous[fresh]
        reverted[fresh] = True
        # Only edges touching a reverted node changed since the last in-mask check.
        check = np.flatnonzero(np.any(np.isin(edges, fresh), axis=1))
    return accepted, int(reverted.sum())


def _flow_fit_graph(coordinates, edges, mask, flow_settings=None, pin_weight=_PIN_WEIGHT):
    """Smooth an extracted graph with the contraction flow, keeping its edges.

    Runs the Laplacian contraction on the graph with EDT retention, the anisotropic
    Laplacian and containment on, and merging off. Endpoints and junctions keep their positions through a very large
    retention weight; the direct LU solver is always used because CG does not
    converge with weights this large. After each step, both ends of any edge leaving the
    foreground, or crossing another edge, return to their previous accepted positions,
    repeatedly, so every accepted step keeps all nodes and edges inside the
    foreground cubes and free of crossings.
    Returns voxel coordinates, unchanged edges, and diagnostics.
    """
    reference = np.asarray(coordinates, dtype=float).copy()
    edges = np.asarray(edges, dtype=int).reshape(-1, 2).copy()
    mask = np.asarray(mask, dtype=bool)
    settings = dict(flow_settings or {})
    forced = {'use_edt', 'use_anisotropic', 'enforce_containment', 'min_edge_length',
              'provisional', 'anchor_scale', 'step_repair', 'binary_segmentation',
              'solver'}
    if forced & set(settings):
        raise ValueError(f'flow_settings cannot set {sorted(forced & set(settings))}.')
    if not np.isfinite(pin_weight) or pin_weight < 1:
        raise ValueError('pin_weight must be finite and >= 1.')
    diagnostics = {'steps': 0, 'repaired_nodes': 0, 'max_pinned_drift': 0.,
                   'pin_weight': float(pin_weight)}
    degree = np.bincount(edges.ravel(), minlength=len(reference))
    if not len(edges) or not np.any(degree == 2):
        return reference, edges, diagnostics
    if _nonincident_intersections(reference, edges, np.ones(3)):
        raise ValueError('Initial graph contains an unintended intersection.')
    if np.any(_edges_leaving_foreground(reference, edges, mask)):
        raise ValueError('Initial graph leaves the foreground mask.')
    n_vertices = len(reference)
    adjacency = sparse.csr_matrix(
        (np.ones(2 * len(edges), dtype=bool),
         (np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]])),
        shape=(n_vertices, n_vertices),
    )
    anchor_scale = np.where(degree == 2, 1., float(pin_weight))

    def repair(previous, proposed):
        accepted, count = _repair_step(previous, proposed, edges, mask)
        diagnostics['steps'] += 1
        diagnostics['repaired_nodes'] += count
        return accepted, count

    output, output_adjacency = laplacian_graph_contraction(
        reference, adjacency, binary_segmentation=mask, use_edt=True,
        use_anisotropic=True, enforce_containment=True, min_edge_length=0.,
        provisional=True, anchor_scale=anchor_scale,
        step_repair=repair, solver='LU', **settings,
    )
    if len(output) != n_vertices or (output_adjacency != adjacency).nnz:
        raise RuntimeError('Flow fitting changed the graph structure.')
    if np.any(_edges_leaving_foreground(output, edges, mask)):
        raise RuntimeError('Flow fitting left the foreground mask.')
    if _nonincident_intersections(output, edges, np.ones(3)):
        raise RuntimeError('Flow fitting introduced an intersection.')
    pinned = degree != 2
    if np.any(pinned):
        diagnostics['max_pinned_drift'] = float(
            np.max(np.linalg.norm(output[pinned] - reference[pinned], axis=1))
        )
    return output, edges, diagnostics


def refine_graph(
    mask,
    contracted_coordinates,
    return_paths=False,
    *,
    voxel_spacing=(1., 1., 1.),
    second_fitting=True,
    flow_settings=None,
):
    """Extract a graph with every foreground tunnel and optionally fit its geometry.

    Parameters
    ----------
    mask : (D, H, W) array
        Original foreground, interpreted with fixed 26-connectivity.
    contracted_coordinates : (N, 3) array
        Laplacian contraction result in the mask's voxel coordinate system.
        Guides which medial voxels survive; never determines tunnel removal.
    return_paths : bool, optional
        Also return reference voxels and the retained edge polylines for export.
    voxel_spacing : tuple of float, optional
        Retained for call compatibility; the flow fit works in voxel units, as
        contraction does. Returned coordinates are in voxel units.
    second_fitting : bool, optional
        Smooth degree-two node positions with the contraction flow; endpoints
        and junctions are held by a very large retention weight. Every extracted
        skeleton node is kept either way, joined by straight edges; without
        fitting, nodes stay at their voxel centres. Default is True.
    flow_settings : dict, optional
        Contraction keyword arguments for the fit: w_L, w_H_base, w_H_medial,
        beta_edt, tol, tol_mean_drift, max_iter and local_pca_hops. EDT retention,
        the anisotropic Laplacian and containment are always on, merging always
        off and the solver always LU. Unset values use the contraction defaults.

    Returns
    -------
    coordinates : (M, 3) array
        Refined graph coordinates in voxel units.
    adjacency : sparse.csr_matrix
        Symmetric adjacency with no redundant independent cycles.
    reference_voxels : (K, 3) array, optional
        Topology-preserving digital skeleton, returned when return_paths is True.
    edge_paths : dict, optional
        Straight edge paths keyed by sorted node-index pairs, returned when
        return_paths is True; each path holds only its two end nodes.
    """
    mask = np.asarray(mask, dtype=bool)
    guidance = np.asarray(contracted_coordinates, dtype=float)
    if mask.ndim != 3 or not np.any(mask):
        raise ValueError('Refinement requires a nonempty 3D foreground mask.')
    if (
        guidance.ndim != 2
        or guidance.shape[1] != 3
        or not len(guidance)
        or not np.all(np.isfinite(guidance))
    ):
        raise ValueError(
            'Contracted coordinates must be a finite nonempty (N, 3) array.'
        )
    # A curve graph cannot represent an enclosed three-dimensional cavity.
    expected_components, expected_tunnels, cavities = foreground_topology(mask)
    if cavities:
        raise ValueError(
            'Foreground contains enclosed cavities; a curve graph cannot preserve their topology.'
        )
    coordinates = _thin_foreground(mask, guidance).astype(float)
    reference_voxels = coordinates.astype(int)
    edges, tunnels = _tunnel_graph(coordinates)
    if second_fitting:
        # Fitting moves node positions only; it never changes the edge set.
        coordinates, edges, diagnostics = _flow_fit_graph(
            coordinates, edges, mask, flow_settings
        )
        print(
            f"Flow fit: {diagnostics['steps']} steps; "
            f"{diagnostics['repaired_nodes']} node moves repaired; "
            f"pin weight {diagnostics['pin_weight']:g}, max endpoint/junction "
            f"drift {diagnostics['max_pinned_drift']:.3g} voxels."
        )
    else:
        print('Second fitting disabled; keeping voxel-centre node positions.')
    # Keep every extracted skeleton node; each edge is its own straight path.
    edges = np.asarray(sorted(map(tuple, edges.tolist())), dtype=int).reshape(-1, 2)
    paths = {(int(u), int(v)): coordinates[[u, v]] for u, v in edges}
    for (u, v), path in paths.items():
        if (not np.array_equal(path[0], coordinates[u])
                or not np.array_equal(path[-1], coordinates[v])):
            raise RuntimeError('Refinement edge path endpoints are inconsistent.')
        for start, end in zip(path[:-1], path[1:]):
            _edge_voxels(start, end, mask.shape, mask)
    if len(edges):
        rows = np.concatenate((edges[:, 0], edges[:, 1]))
        cols = np.concatenate((edges[:, 1], edges[:, 0]))
    else:
        rows = cols = np.array([], dtype=int)
    adjacency = sparse.csr_matrix(
        (np.ones(len(rows), dtype=bool), (rows, cols)),
        shape=(len(coordinates), len(coordinates)),
    )
    components = sparse.csgraph.connected_components(adjacency, directed=False)[0]
    if (
        components != expected_components
        or tunnels != expected_tunnels
        or len(edges) - len(coordinates) + components != expected_tunnels
    ):
        raise RuntimeError('Refinement failed its foreground topology checks.')
    print(
        f'Refined graph: {len(coordinates)} nodes, {len(edges)} edges, '
        f'{components} components, {tunnels} independent tunnels preserved.'
    )
    if return_paths:
        return coordinates, adjacency, reference_voxels, paths
    return coordinates, adjacency
