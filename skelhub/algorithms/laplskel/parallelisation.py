"""Per-component processing, run through joblib.

Changes from upstream (no numerical effect):

- ``tqdm_joblib.ParallelPbar`` is replaced by plain ``joblib.Parallel`` with the
  same ``n_jobs`` and ``batch_size``, so the task order and results are unchanged
  and only the progress bar is gone.
- ``process_components`` takes ``quiet``; when True each worker runs with its
  standard output discarded, so worker processes stay silent too.
"""

import contextlib
import io
import os

import numpy as np
from joblib import Parallel, delayed
from scipy.ndimage import find_objects
from scipy.spatial import KDTree

from .contraction import laplacian_graph_contraction
from .graph import compute_sparse_adjacency_matrix
from .refinement import DEFAULT_FIT_W_H, DEFAULT_FIT_W_H_MEDIAL, refine_graph


def _process_single_label(
    label_id,
    cropped_label,
    offset_origin,
    beta_edt,
    w_L,
    w_H_base,
    w_H_medial,
    tol_max_drift,
    init_graph_adj,
    local_pca_hops,
    decimate_ratio,
    min_edge_length,
    num_features,
    solver,
    voxel_spacing=(1.0, 1.0, 1.0),
    graph_original=False,
    second_fitting=False,
    tol_mean_drift=0.0025,
    max_iter=500,
    fit_w_H=DEFAULT_FIT_W_H,
    fit_w_H_medial=DEFAULT_FIT_W_H_MEDIAL,
):
    """
    Worker function to process a single connected component label.

    Contraction always uses EDT-scaled retention, the anisotropic Laplacian and
    hard foreground containment.

    Parameters
    ----------
    label_id : int
        ID of current label
    cropped_label : np.ndarray
        Boolean component mask with a one-voxel background halo.
    offset_origin : tuple
        Global-volume origin corresponding to local crop coordinate zero.
    beta_edt : float
        Scaling modulation weight assigned to boundary energy calculation properties.
        Shared by contraction and the second fit.
    w_L : float
        Contraction weight step modifier targeting structural local geometric collapse.
        This should be alpha in Damseh 2021. Shared by contraction and the second fit.
    w_H_base : float
        Baseline contraction retention weight. This should be equivalent to beta in
        Damseh 2021. The second fit uses fit_w_H instead.
    w_H_medial : float
        Multiplicative contraction retention boost applied to nodes at or around
        inscribed-sphere centres. A value of 1.0 disables the boost. The second fit
        uses fit_w_H_medial instead.
    tol_max_drift : float
        Maximum displacement in voxels for three stable steps; also the small-step
        decimation threshold. Shared by contraction and the second fit.
    init_graph_adj : {6, 18, 26}, int
        Voxel-neighborhood connectivity used to construct the initial graph.
    local_pca_hops : int
        Number of graph hops included in each node's neighborhood when estimating
        local tangent directions. Shared by contraction and the second fit.
    decimate_ratio : float
        Adaptive decimation threshold in (0, 1] for consecutive mean-drift ratios.
    min_edge_length : float
        The Euclidean spatial threshold criteria below which two connected nodes undergo
        structural merging, expressed as a fraction of the isotropic voxel length.
    num_features : int
        Number of extracted labels.
    solver : ['LU', 'CG', 'AMGCG'], string, optional
        The contraction linear solver. LU uses SuperLU, a direct solver, CG uses
        Conjugate Gradient (iterative solver), better for memory on big data, AMGCG
        constructs an Algebraic Multigrid (AMG) preconditioner before running CG,
        which makes it far faster, but may require a tad more memory. The second fit
        always uses LU.
    voxel_spacing : tuple of float, optional
        Physical voxel spacing, forwarded to refinement.
    graph_original : bool, optional
        Append pre-refinement coordinates and adjacency.
    second_fitting : bool, optional
        Smooth the extracted graph's node positions with the contraction flow. It
        shares the contraction settings above except the retention weights, which
        come from fit_w_H and fit_w_H_medial. Default False.
    tol_mean_drift : float, optional
        Mean displacement in voxels for three stable steps; zero disables it.
        Shared by contraction and the second fit. Default is 0.0025.
    max_iter : int, optional
        Maximum iterations of contraction and of the second fit. Default is 500.
    fit_w_H : float, optional
        Baseline retention weight of the second fit. Default is 0.16.
    fit_w_H_medial : float, optional
        Medial retention boost of the second fit. Default is 3.

    Returns
    -------
    label_id : int
        ID of current label (For tracking)
    contracted_X : numpy.ndarray
        An (M, 3) matrix mapping the continuous 3D spatial points along the skeleton path.
    final_adj : scipy.sparse.csr_matrix
        The resulting graph sparse adjacency connectivity representation of shape (M, M).
    reference_voxels : numpy.ndarray
        Digital skeleton coordinates in the global volume.
    edge_paths : dict
        Straight edge paths in global coordinates, each holding its two end nodes.
    intermediate_X, intermediate_adj : numpy.ndarray, scipy.sparse.csr_matrix
        Appended only when graph_original is enabled. Global coordinates and
        adjacency before refinement; components with at most three voxels retain
        their initial graph because contraction is skipped.
    """
    X_init_local = np.argwhere(cropped_label).astype(np.uint16)
    intermediate = ()
    # Second fitting reuses the contraction objective and stopping settings, with
    # its own retention weights.
    flow_settings = dict(
        beta_edt=beta_edt, w_L=w_L, w_H_base=fit_w_H, w_H_medial=fit_w_H_medial,
        tol=tol_max_drift, tol_mean_drift=tol_mean_drift, max_iter=max_iter,
        local_pca_hops=local_pca_hops,
    )
    refine_options = dict(
        return_paths=True, voxel_spacing=voxel_spacing,
        second_fitting=second_fitting, flow_settings=flow_settings,
    )
    # Skip contraction on small noise components
    if len(X_init_local) <= 3:
        if graph_original:
            intermediate = (
                X_init_local + np.array(offset_origin, dtype=np.float32),
                compute_sparse_adjacency_matrix(KDTree(X_init_local), init_graph_adj),
            )
        refined, adj_sparse, voxels, paths = refine_graph(
            cropped_label, X_init_local, **refine_options
        )
        X_init_global = refined + np.array(offset_origin, dtype=np.float32)
        return (
            label_id, X_init_global, adj_sparse, voxels + offset_origin,
            {edge: path + offset_origin for edge, path in paths.items()},
        ) + intermediate

    print(
        f'\n--- Processing Label {label_id}/{num_features} ({X_init_local.sum()} voxels) ---'
    )

    # Contraction followed by topology-preserving refinement.
    print(f'Computing {init_graph_adj}-connected voxel graph...')
    adj_sparse = compute_sparse_adjacency_matrix(
        KDTree(X_init_local), init_graph_adj
    )
    label_X_local, label_adj = laplacian_graph_contraction(
        X_init_local,
        adj_sparse,
        binary_segmentation=cropped_label,
        use_edt=True,
        use_anisotropic=True,
        enforce_containment=True,
        beta_edt=beta_edt,
        w_L=w_L,
        w_H_base=w_H_base,
        w_H_medial=w_H_medial,
        tol=tol_max_drift,
        tol_mean_drift=tol_mean_drift,
        max_iter=max_iter,
        local_pca_hops=local_pca_hops,
        decimate_ratio=decimate_ratio,
        min_edge_length=min_edge_length,
        solver=solver,
    )

    if graph_original:
        intermediate = (
            label_X_local + np.array(offset_origin, dtype=np.float32),
            label_adj.copy(),
        )

    label_X_local, label_adj, voxels, paths = refine_graph(
        cropped_label, label_X_local, **refine_options
    )
    label_X_global = label_X_local + np.array(offset_origin, dtype=np.float32)

    return (
        label_id, label_X_global, label_adj, voxels + offset_origin,
        {edge: path + offset_origin for edge, path in paths.items()},
    ) + intermediate


def _process_single_label_quietly(*args):
    """Run ``_process_single_label`` with its standard output discarded."""
    with contextlib.redirect_stdout(io.StringIO()):
        return _process_single_label(*args)


def _padded_component_crop(labeled_volume, label_id, bounding_box):
    """Return one tightly cropped component with a one-voxel background halo."""
    component = labeled_volume[bounding_box] == label_id
    padded_component = np.pad(component, 1, mode='constant', constant_values=False)
    offset_origin = tuple(axis.start - 1 for axis in bounding_box)
    return padded_component, offset_origin


def process_components(
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
    voxel_spacing=(1.0, 1.0, 1.0),
    graph_original=False,
    second_fitting=False,
    tol_mean_drift=0.0025,
    max_iter=500,
    fit_w_H=DEFAULT_FIT_W_H,
    fit_w_H_medial=DEFAULT_FIT_W_H_MEDIAL,
    quiet=False,
):
    """Process labeled segmentation components in parallel."""
    worker = _process_single_label_quietly if quiet else _process_single_label
    total_cores = os.cpu_count() or 1
    if n_jobs is None or n_jobs <= 0:
        n_workers = max(1, int(np.floor(0.30 * total_cores)))
    else:
        n_workers = min(n_jobs, total_cores)

    print(
        f'Processing {num_features} components in parallel using {n_workers} worker(s) '
        f'on {total_cores} CPU cores detected.'
    )

    slices_list = find_objects(labeled_volume)

    tasks = []
    for label_id in range(1, num_features + 1):
        bbox_slice = slices_list[label_id - 1]

        if bbox_slice is None:
            continue

        cropped_label, offset_origin = _padded_component_crop(
            labeled_volume, label_id, bbox_slice
        )

        tasks.append(
            delayed(worker)(
                label_id,
                cropped_label,
                offset_origin,
                beta_edt,
                w_L,
                w_H_base,
                w_H_medial,
                tol_max_drift,
                init_graph_adj,
                local_pca_hops,
                decimate_ratio,
                min_edge_length,
                num_features,
                solver,
                voxel_spacing,
                graph_original,
                second_fitting,
                tol_mean_drift,
                max_iter,
                fit_w_H,
                fit_w_H_medial,
            )
        )

    results = Parallel(n_jobs=n_workers, batch_size=1)(tasks)

    return results
