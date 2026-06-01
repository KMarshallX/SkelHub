# Laplacian Backend Notes

This note summarizes the current `laplacian` backend workflow as implemented in
`skelhub.algorithms.laplacian`.

## High-Level Workflow

```text
function run_laplacian_backend(volume, config):
    # Validate and binarize the input volume.
    data = as_array(volume.data)
    require data.ndim == 3

    binary = data > 0
    input_voxels = count_nonzero(binary)

    # Empty inputs short-circuit before graph construction.
    if input_voxels == 0:
        return empty SkeletonResult

    # Split disconnected foreground objects so each one contracts independently.
    labeled_volume, components = label_26_connected_components(binary)

    # Accumulate per-component raster and graph outputs in full-volume space.
    full_skeleton = zeros_like(binary)
    cleaned_component_graphs = []
    original_component_graphs = []
    component_metadata = []

    for component_index, component in enumerate(components, start=1):
        # Work on a tight crop, while remembering its full-volume offset.
        bbox = component.bbox
        offset = bbox.start
        component_mask = labeled_volume[bbox] == component.label

        # Run the graph-native Laplacian pipeline on this one component.
        cleaned_graph, original_graph, metadata = skeletonize_component(
            component_mask,
            config,
        )

        # Current standard NIfTI output uses the refined pre-cleaning graph.
        skeleton_crop = rasterize_graph_26conn(
            original_graph,
            shape=component_mask.shape,
        )
        full_skeleton[bbox] = full_skeleton[bbox] OR skeleton_crop

        # Store cleaned graph for GraphML output and SkeletonResult.graph.
        if cleaned_graph is not empty:
            cleaned_component_graphs.append(
                (cleaned_graph, offset, component_index, component.label)
            )

        # Store refined pre-cleaning graph for optional graph_original export.
        if original_graph is not empty:
            original_component_graphs.append(
                (original_graph, offset, component_index, component.label)
            )

        component_metadata.append(metadata plus component summary)

    # Shift cropped graph coordinates back into full-volume voxel coordinates.
    cleaned_graph_full = aggregate_component_graphs(cleaned_component_graphs)
    original_graph_full = aggregate_component_graphs(original_component_graphs)

    # Graph exports are optional backend-specific outputs.
    if config.graph_output is set:
        write cleaned_graph_full as GraphML

    if config.graph_original is set:
        write original_graph_full as GraphML

    # Return the framework-standard result object.
    return SkeletonResult(
        skeleton=full_skeleton,
        graph=cleaned_graph_full as GraphResult,
        backend_metadata=aggregated_laplacian_metadata,
    )
```

## Per-Component Skeletonization

```text
function skeletonize_component(component_mask, config):
    # Component masks are already cropped, but are normalized to boolean here.
    binary = component_mask > 0

    # 1. Build the initial dense voxel graph.
    # Each foreground voxel becomes part of the geometric graph.
    generator = GenerateGraph(binary)
    generator.UpdateGridGraph(Sampling=config.sampling)
    initial_graph = generator.GetOutput()

    # 2. Run Laplacian graph contraction.
    # Node positions are iteratively moved and clustered toward centerlines.
    contract = ContractGraph(initial_graph)
    contract.Update(
        DistParam=config.dist_param,
        MedParam=config.med_param,
        SpeedParam=config.speed_param,
        DegreeThreshold=config.degree_threshold,
        ClusteringResolution=config.clustering_r,
        StopParam=config.stop_param,
        NFreeIteration=config.n_free_iteration,
    )
    contracted_graph = contract.GetOutput()

    # 3. Refine small polygon artifacts left after contraction.
    # This collapses small residual cycles before the final cleaning pass.
    refine = RefineGraph(contracted_graph)
    refine.Update(
        AreaParam=config.area_param,
        PolyParam=config.poly_param,
    )
    refined_graph = fix_graph(refine.GetOutput())

    # 4. Clean degree-2 nodes while preserving continuity.
    # This simplifies chains, but does not remove arbitrary short spurs.
    cleaned_graph = post_node_cleaning(refined_graph)

    # Keep enough counters to summarize each component and aggregate the run.
    metadata = {
        initial node and edge counts,
        refined node and edge counts,
        cleaned node and edge counts,
        final contraction cycle area,
        contraction iteration count,
        max-iteration flag,
    }

    # cleaned_graph is the decimated graph; refined_graph is graph_original.
    return cleaned_graph, refined_graph, metadata
```

## Important Current Behavior

- Foreground connected-component analysis uses 26-connectivity.
- Each component is processed independently in a tight cropped bounding box.
- Component graph coordinates are shifted back into full-volume voxel space during graph aggregation.
- The cleaned graph is used for `--graph_output` and `SkeletonResult.graph`.
- The standard output skeleton volume is rasterized from the refined pre-cleaning graph, recorded in metadata as `rasterized_output_source: graph_original`.
- Current node cleaning only removes degree-2 nodes and reconnects their neighbors; it does not perform general short-spur or false-branch pruning.

## Modified Per-Component Skeletonization

```text
function skeletonize_component_topology_safe(component_mask, config):
    binary = component_mask > 0

    # 0. Precompute maps.
    D = distance_transform_edt(binary)
    labels = connected_components(binary, connectivity=config.connectivity)
    input_topology = compute_topology(binary)

    # 1. Build initial dense voxel graph with provenance.
    generator = GenerateGraph(binary)
    generator.UpdateGridGraph(Sampling=config.sampling)
    initial_graph = generator.GetOutput()

    initial_graph = attach_node_attributes(
        initial_graph,
        binary=binary,
        D=D,
        labels=labels,
        origin_voxels=True,
    )

    validate_graph(
        initial_graph,
        binary=binary,
        labels=labels,
        topology_ref=input_topology,
        require_nodes_inside=True,
        require_edges_foreground_supported=True,
    )

    # 2. Run constrained Laplacian contraction.
    contract = ContractGraphTopologySafe(initial_graph)
    contract.Update(
        DistParam=config.dist_param,
        MedParam=config.med_param,
        SpeedParam=config.speed_param,
        DegreeThreshold=config.degree_threshold,

        # modified controls
        ClusteringResolution=config.clustering_r,
        StopParam=config.stop_param,
        NFreeIteration=config.n_free_iteration,

        # new constraints
        ForegroundMask=binary,
        DistanceMap=D,
        ComponentLabels=labels,
        ProjectionMode="foreground_medial",
        AnchorMode="distance_endpoint_branch",
        TopologySafeClustering=True,
        EdgeSupportCheck=True,
        PreserveBeta0=True,
        PreserveBeta1=config.preserve_beta1,
    )

    contracted_graph = contract.GetOutput()

    validate_graph(
        contracted_graph,
        binary=binary,
        labels=labels,
        topology_ref=input_topology,
        require_nodes_inside=True,
        require_edges_foreground_supported=True,
    )

    # 3. Optional topology-safe refinement.
    if config.enable_refine:
        refine = RefineGraphTopologySafe(contracted_graph)
        refine.Update(
            AreaParam=config.area_param,
            PolyParam=config.poly_param,
            ForegroundMask=binary,
            DistanceMap=D,
            PreserveBeta0=True,
            PreserveBeta1=config.preserve_beta1,
            RejectBackgroundCrossing=True,
        )
        refined_graph = refine.GetOutput()
    else:
        refined_graph = contracted_graph

    refined_graph = fix_graph_conservative(
        refined_graph,
        binary=binary,
        labels=labels,
        preserve_topology=True,
    )

    validate_graph(
        refined_graph,
        binary=binary,
        labels=labels,
        topology_ref=input_topology,
        require_nodes_inside=True,
        require_edges_foreground_supported=True,
    )

    # 4. Clean degree-2 nodes but preserve polylines.
    cleaned_graph = post_node_cleaning_topology_safe(
        refined_graph,
        binary=binary,
        preserve_polyline_geometry=True,
        preserve_topology=True,
    )

    validate_graph(
        cleaned_graph,
        binary=binary,
        labels=labels,
        topology_ref=input_topology,
        require_nodes_inside=True,
        require_edges_foreground_supported=True,
    )

    metadata = collect_metadata(
        input_topology=input_topology,
        initial_graph=initial_graph,
        contracted_graph=contracted_graph,
        refined_graph=refined_graph,
        cleaned_graph=cleaned_graph,
        validation_reports=True,
    )

    return cleaned_graph, refined_graph, metadata
```