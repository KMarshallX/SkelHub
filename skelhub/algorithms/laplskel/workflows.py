"""In-memory laplskel workflow: mask in, skeleton and optional graph files out.

Changes from upstream (no numerical effect):

- Upstream ``laplacian_skeletonisation(nifti_path, out_path, ...)`` loaded the mask
  with ``nigsp.io.load_nifti_get_mask`` and wrote the NIfTI with
  ``nigsp.io.export_nifti``. Here the workflow starts at that mask-loading
  boundary: ``laplacian_skeletonisation_from_mask`` takes the boolean mask, its
  affine and voxel spacing. The SkelHub backend builds the mask exactly as
  upstream did, and the SkelHub framework writes the skeleton NIfTI.
- Output-path validation is split into ``validated_output_files`` so it can run
  before any computation, and it also accepts the framework's NIfTI path
  (``reserved_outputs``) for the collision check.
- The function returns the per-component results as a fourth value, and accepts
  ``quiet`` (forwarded to ``process_components``).
- ``_graph_files`` and ``_write_graph`` are unchanged. Everything after mask
  loading (the empty-mask check, component labelling, processing, merging,
  rasterization and graph writing) keeps upstream's operations and order.
"""

import os

import numpy as np
from scipy import sparse

from .parallelisation import process_components
from .refinement import DEFAULT_FIT_W_H, DEFAULT_FIT_W_H_MEDIAL
from .utils import coords_to_dense_3d, label_and_sort_by_size, write_graphml


def _graph_files(path, option):
    """Return the files one graph output writes; its ending selects the format.

    A .graphml path is written as GraphML. A .npz path holds the sparse adjacency,
    with coordinates (and edge paths, if any) in <stem>_coords.npz beside it.
    """
    path = os.fspath(path)
    stem, extension = os.path.splitext(path)
    if extension.lower() == '.graphml' and stem:
        return [path]
    if extension.lower() == '.npz' and stem:
        return [path, f'{stem}_coords.npz']
    raise ValueError(f'{option} must end in .graphml or .npz, got {path!r}.')


def _write_graph(path, coordinates, adjacency, **graphml_options):
    """Write one graph to a .graphml or .npz path (see _graph_files)."""
    path = os.fspath(path)
    stem, extension = os.path.splitext(path)
    if extension.lower() == '.graphml':
        write_graphml(coordinates, adjacency, output_path=path, **graphml_options)
        return
    arrays = dict(contracted_X=coordinates)
    edge_paths = graphml_options.get('edge_paths')
    if edge_paths is not None:
        ordered_edges = sorted(edge_paths)
        paths = [edge_paths[edge] for edge in ordered_edges]
        arrays.update(
            edge_path_nodes=np.asarray(ordered_edges, dtype=int).reshape(-1, 2),
            edge_path_offsets=np.cumsum([0] + [len(path) for path in paths]),
            edge_path_points=np.vstack(paths) if paths else np.empty((0, 3)),
        )
    np.savez_compressed(f'{stem}_coords.npz', **arrays)
    sparse.save_npz(path, adjacency)


def validated_output_files(graph_output=None, graph_original=None, reserved_outputs=()):
    """Return the absolute paths of every output file, rejecting bad suffixes and clashes.

    ``reserved_outputs`` holds files written by someone else (the framework's
    skeleton NIfTI), which the graph files must not overwrite.
    """
    output_files = [os.fspath(path) for path in reserved_outputs]
    for option, path in (('graph_output', graph_output),
                         ('graph_original', graph_original)):
        if path is not None:
            output_files += _graph_files(path, option)
    resolved = [os.path.abspath(path) for path in output_files]
    if len(set(resolved)) != len(resolved):
        raise ValueError(f'Output paths must be distinct files, got {output_files}.')
    return resolved


def laplacian_skeletonisation_from_mask(
    volume_data,
    affine,
    voxel_spacing,
    beta_edt=1.0,
    w_L=0.5,
    w_H_base=0.5,
    w_H_medial=20.0,
    tol_max_drift=0.05,
    tol_mean_drift=0.0025,
    max_iter=500,
    decimate_ratio=0.93,
    min_edge_length=0.01,
    separate_streams=False,
    label_connectivity=26,
    init_graph_adj=26,
    local_pca_hops=1,
    solver='CG',
    n_jobs=None,
    graph_output=None,
    graph_original=None,
    second_fitting=False,
    fit_w_H=DEFAULT_FIT_W_H,
    fit_w_H_medial=DEFAULT_FIT_W_H_MEDIAL,
    reserved_outputs=(),
    quiet=False,
):
    """
    Skeletonise a boolean mask by Laplacian graph contraction and refinement.

    Contraction always uses EDT-scaled retention, the anisotropic Laplacian and
    hard foreground containment. Parameters match upstream
    ``laplacian_skeletonisation``; only the input and output handling differ.

    Parameters
    ----------
    volume_data : numpy.ndarray
        Boolean 3D foreground mask in voxel-index order (upstream:
        ``nigsp.io.load_nifti_get_mask(path, is_mask=True, ndim=3)``).
    affine : numpy.ndarray
        4x4 voxel-to-world affine, used for GraphML world coordinates.
    voxel_spacing : tuple of float
        Voxel spacing, forwarded to refinement (which keeps it only for call
        compatibility; all work is in voxel units).
    reserved_outputs : sequence of str, optional
        Files written by the caller (the skeleton NIfTI). Graph outputs may not
        collide with them, and their folders are created before processing.
    quiet : bool, optional
        Discard the per-component progress output of worker processes.

    Returns
    -------
    contracted_X : numpy.ndarray
        (M, 3) skeleton graph node coordinates in voxel units. Without
        second_fitting, these are the digital skeleton voxel centres.
    final_adj : scipy.sparse.csr_matrix
        (M, M) skeleton graph adjacency.
    nifti_skel : numpy.ndarray
        Boolean digital skeleton on the input grid.
    results : list of tuple
        Per-component results from ``process_components``.

    Raises
    ------
    ValueError
        If an option is invalid, an output path is invalid or repeated, or the
        mask has no foreground.
    """
    if not np.isfinite(decimate_ratio) or not 0 < decimate_ratio <= 1:
        raise ValueError('decimate_ratio must be finite and in (0, 1].')
    if not np.isfinite(tol_mean_drift) or tol_mean_drift < 0:
        raise ValueError('tol_mean_drift must be finite and >= 0.')
    if (
        isinstance(max_iter, (bool, np.bool_))
        or not isinstance(max_iter, (int, np.integer))
        or max_iter < 1
    ):
        raise ValueError('max_iter must be a positive integer.')
    if not np.isfinite(fit_w_H) or fit_w_H <= 0:
        raise ValueError('fit_w_H must be finite and > 0.')
    if not np.isfinite(fit_w_H_medial) or fit_w_H_medial < 1:
        raise ValueError('fit_w_H_medial must be finite and >= 1.')
    if separate_streams and label_connectivity != 26:
        raise ValueError(
            'Tunnel preservation requires --label_connectivity 26 '
            'when separating streams.'
        )
    resolved = validated_output_files(graph_output, graph_original, reserved_outputs)
    # Create output folders first, so a bad path fails before processing.
    for folder in {os.path.dirname(path) for path in resolved}:
        os.makedirs(folder, exist_ok=True)

    volume_data = np.asarray(volume_data)
    if volume_data.dtype != bool or volume_data.ndim != 3:
        raise ValueError('volume_data must be a boolean 3D mask.')

    if not np.any(volume_data):
        raise ValueError('Provided segmentation volume lacks any foreground structure.')

    # Process each component independently if separate_streams is True
    if separate_streams:
        labeled_volume, num_features = label_and_sort_by_size(
            volume_data, label_connectivity
        )
    else:
        labeled_volume, num_features = volume_data * 1, 1

    results = process_components(
        labeled_volume,
        num_features,
        beta_edt,
        w_L,
        w_H_base,
        w_H_medial,
        tol_max_drift,
        init_graph_adj,
        local_pca_hops,
        decimate_ratio,
        min_edge_length,
        n_jobs,
        solver,
        voxel_spacing,
        graph_original is not None,
        second_fitting,
        tol_mean_drift,
        max_iter,
        fit_w_H,
        fit_w_H_medial,
        quiet=quiet,
    )

    print('Reuniting results from parallel jobs.')

    if not results:
        raise ValueError('No valid components found for contraction.')

    # Merge coordinates and sparse block-diagonal adjacency matrices across all labels
    contracted_X = np.vstack([res[1] for res in results])
    final_adj = sparse.block_diag([res[2] for res in results], format='csr')
    # Keep the digital reference and edge paths: rounding simplified straight
    # segments can create extra voxel loops even when graph topology is correct.
    digital_voxels = np.vstack([res[3] for res in results])
    nifti_skel = coords_to_dense_3d(digital_voxels, volume_data.shape)
    edge_paths = {}
    node_offset = 0
    for result in results:
        edge_paths.update({
            (u + node_offset, v + node_offset): path
            for (u, v), path in result[4].items()
        })
        node_offset += len(result[1])

    if graph_output is not None:
        print(f'\nSaving skeleton graph to {graph_output}')
        labels = np.concatenate(
            [np.full(len(res[1]), res[0], dtype=int) for res in results]
        )
        _write_graph(
            graph_output, contracted_X, final_adj, component_labels=labels,
            affine=affine, volume_shape=volume_data.shape,
            binary_segmentation=volume_data, edge_paths=edge_paths,
        )
    if graph_original is not None:
        print(f'Saving contracted graph before thinning to {graph_original}')
        _write_graph(
            graph_original,
            np.vstack([res[5] for res in results]),
            sparse.block_diag([res[6] for res in results], format='csr'),
            component_labels=np.concatenate(
                [np.full(len(res[5]), res[0], dtype=int) for res in results]
            ),
            affine=affine,
            volume_shape=volume_data.shape,
        )

    return contracted_X, final_adj, nifti_skel, results
