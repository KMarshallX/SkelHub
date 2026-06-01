#!/usr/bin/env python3
"""Crop foreground and graph patches for GraphML nodes outside a foreground mask."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

import igraph as ig
import nibabel as nib
import numpy as np
from scipy import ndimage


CONNECTIVITY_26 = np.ones((3, 3, 3), dtype=np.uint8)


@dataclass(frozen=True, slots=True)
class LoadedNifti:
    path: Path
    image: nib.Nifti1Image
    data: np.ndarray
    affine: np.ndarray
    header: nib.Nifti1Header


@dataclass(frozen=True, slots=True)
class ComponentCrop:
    label: int
    bbox: tuple[slice, slice, slice]
    buffered_bbox: tuple[slice, slice, slice]
    escaping_nodes: int


@dataclass(frozen=True, slots=True)
class GraphNodeInfo:
    index: int
    voxel_pos: np.ndarray
    rounded: np.ndarray
    in_bounds: bool
    inside_foreground: bool
    component_label: int | None


@dataclass(frozen=True, slots=True)
class GraphCheckResult:
    graph: ig.Graph
    nodes: tuple[GraphNodeInfo, ...]
    inside_count: int
    escaping_by_component: dict[int, list[GraphNodeInfo]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find GraphML nodes outside a foreground NIfTI mask and crop aligned "
            "NIfTI/GraphML patches for affected connected components."
        )
    )
    parser.add_argument("--input-fore", required=True, help="Input foreground NIfTI used for checks and CCA.")
    parser.add_argument("--input-graph", required=True, help="Input GraphML checked for escaping nodes.")
    parser.add_argument("--nif-path", required=True, help="Output directory for cropped NIfTI patches.")
    parser.add_argument(
        "--grapa-path",
        required=True,
        help="Output directory for cropped GraphML patches. Spelling is intentional.",
    )
    parser.add_argument("--input-img", help="Optional original/intensity NIfTI cropped by the same bboxes.")
    parser.add_argument("--input-skel", help="Optional skeleton NIfTI cropped by the same bboxes.")
    parser.add_argument("--input-graph2", help="Optional additional GraphML cropped by the same bboxes.")
    return parser.parse_args()


def _require_file(path: str | Path, *, label: str) -> Path:
    resolved = Path(path).expanduser()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} does not exist or is not a file: {resolved}")
    return resolved


def load_nifti(path: str | Path, *, label: str) -> LoadedNifti:
    input_path = _require_file(path, label=label)
    image = nib.load(str(input_path))
    if not isinstance(image, nib.Nifti1Image):
        image = nib.Nifti1Image.from_image(image)
    data = np.asanyarray(image.dataobj)
    if data.ndim != 3:
        raise ValueError(f"{label} must be a 3D NIfTI volume. Got shape={data.shape}.")
    return LoadedNifti(
        path=input_path,
        image=image,
        data=np.asarray(data),
        affine=np.asarray(image.affine, dtype=float),
        header=image.header.copy(),
    )


def _load_json_point(value: object, *, label: str) -> np.ndarray:
    try:
        raw = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain JSON coordinates.") from exc
    point = np.asarray(raw, dtype=float)
    if point.shape != (3,) or not np.isfinite(point).all():
        raise ValueError(f"{label} must contain three finite coordinates.")
    return point


def _integer_component_label(value: object) -> int | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number) or not number.is_integer():
        return None
    label = int(number)
    return label if label > 0 else None


def _graph_component_label(vertex: ig.Vertex, attrs: set[str]) -> int | None:
    if "component_label" not in attrs:
        return None
    return _integer_component_label(vertex["component_label"])


def load_graph(path: str | Path, *, label: str) -> ig.Graph:
    graph_path = _require_file(path, label=label)
    graph = ig.Graph.Read_GraphML(str(graph_path))
    if "voxel_pos" not in graph.vs.attributes():
        raise ValueError(f"{label} must contain node attribute 'voxel_pos': {graph_path}")
    return graph


def label_foreground(foreground: np.ndarray) -> tuple[np.ndarray, list[tuple[slice, slice, slice] | None]]:
    binary = np.asarray(foreground) > 0
    labeled, count = ndimage.label(binary, structure=CONNECTIVITY_26)
    objects = ndimage.find_objects(labeled, max_label=int(count))
    return labeled, list(objects)


def check_graph_nodes(
    graph: ig.Graph,
    foreground: np.ndarray,
    labeled: np.ndarray,
) -> GraphCheckResult:
    shape = np.asarray(foreground.shape, dtype=int)
    attrs = set(graph.vs.attributes())
    nodes: list[GraphNodeInfo] = []
    escaping_by_component: dict[int, list[GraphNodeInfo]] = {}
    inside_count = 0
    missing_labels = 0

    for vertex in graph.vs:
        voxel_pos = _load_json_point(vertex["voxel_pos"], label=f"node {vertex.index} voxel_pos")
        rounded = np.rint(voxel_pos).astype(int)
        in_bounds = bool(np.all((rounded >= 0) & (rounded < shape)))
        inside = bool(in_bounds and foreground[tuple(rounded)] > 0)
        component_label = _graph_component_label(vertex, attrs)

        info = GraphNodeInfo(
            index=int(vertex.index),
            voxel_pos=voxel_pos,
            rounded=rounded,
            in_bounds=in_bounds,
            inside_foreground=inside,
            component_label=component_label,
        )
        nodes.append(info)

        if inside:
            inside_count += 1
            continue

        if component_label is None and in_bounds:
            mapped_label = int(labeled[tuple(rounded)])
            component_label = mapped_label if mapped_label > 0 else None
        if component_label is None:
            missing_labels += 1
            continue
        escaping_by_component.setdefault(component_label, []).append(info)

    if missing_labels:
        raise ValueError(
            "Graph contains escaping nodes without usable component_label, and they could not be "
            f"mapped to a foreground component by rounded voxel coordinate. Count={missing_labels}."
        )

    return GraphCheckResult(
        graph=graph,
        nodes=tuple(nodes),
        inside_count=inside_count,
        escaping_by_component=escaping_by_component,
    )


def _buffer_bbox(
    bbox: tuple[slice, slice, slice],
    shape: tuple[int, int, int],
    *,
    buffer: int = 1,
) -> tuple[slice, slice, slice]:
    buffered = []
    for axis, axis_slice in enumerate(bbox):
        start = max(int(axis_slice.start or 0) - buffer, 0)
        stop = min(int(axis_slice.stop or 0) + buffer, int(shape[axis]))
        buffered.append(slice(start, stop))
    return tuple(buffered)  # type: ignore[return-value]


def _bbox_start(bbox: tuple[slice, slice, slice]) -> np.ndarray:
    return np.asarray([int(axis.start or 0) for axis in bbox], dtype=float)


def _bbox_name(bbox: tuple[slice, slice, slice]) -> str:
    return (
        f"x{int(bbox[0].start or 0)}-{int(bbox[0].stop or 0)}"
        f"_y{int(bbox[1].start or 0)}-{int(bbox[1].stop or 0)}"
        f"_z{int(bbox[2].start or 0)}-{int(bbox[2].stop or 0)}"
    )


def _translation(offset: np.ndarray) -> np.ndarray:
    matrix = np.eye(4, dtype=float)
    matrix[:3, 3] = np.asarray(offset, dtype=float)
    return matrix


def _offset_affine(image: nib.Nifti1Image, offset: np.ndarray) -> tuple[np.ndarray, np.ndarray, int, np.ndarray, int]:
    transform = _translation(offset)
    affine = np.asarray(image.affine, dtype=float) @ transform
    qform, qcode = image.get_qform(coded=True)
    sform, scode = image.get_sform(coded=True)
    qbase = np.asarray(image.affine if qform is None else qform, dtype=float)
    sbase = np.asarray(image.affine if sform is None else sform, dtype=float)
    return (
        affine,
        qbase @ transform,
        int(qcode) if qcode else 1,
        sbase @ transform,
        int(scode) if scode else 1,
    )


def write_nifti_patch(
    source: LoadedNifti,
    patch_data: np.ndarray,
    bbox: tuple[slice, slice, slice],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    affine, qform, qcode, sform, scode = _offset_affine(source.image, _bbox_start(bbox))
    header = source.header.copy()
    image = nib.Nifti1Image(np.asarray(patch_data), affine, header)
    image.set_data_dtype(np.asarray(patch_data).dtype)
    image.set_qform(qform, qcode)
    image.set_sform(sform, scode)
    nib.save(image, str(output_path))


def _component_crops(
    labels: Iterable[int],
    objects: list[tuple[slice, slice, slice] | None],
    shape: tuple[int, int, int],
    escaping_by_component: dict[int, list[GraphNodeInfo]],
) -> list[ComponentCrop]:
    crops: list[ComponentCrop] = []
    for label in sorted(labels):
        if label < 1 or label > len(objects) or objects[label - 1] is None:
            raise ValueError(f"Escaping node references missing foreground component_label={label}.")
        bbox = objects[label - 1]
        assert bbox is not None
        crops.append(
            ComponentCrop(
                label=int(label),
                bbox=bbox,
                buffered_bbox=_buffer_bbox(bbox, shape),
                escaping_nodes=len(escaping_by_component[label]),
            )
        )
    return crops


def _patch_filename(prefix: str, crop: ComponentCrop, extension: str) -> str:
    return f"{prefix}_component_label_{crop.label:04d}_bbox_{_bbox_name(crop.buffered_bbox)}{extension}"


def _write_foreground_patch(
    foreground: LoadedNifti,
    labeled: np.ndarray,
    crop: ComponentCrop,
    output_dir: Path,
) -> Path:
    crop_labels = labeled[crop.buffered_bbox]
    source_crop = foreground.data[crop.buffered_bbox]
    patch = np.zeros(source_crop.shape, dtype=foreground.data.dtype)
    component_mask = crop_labels == crop.label
    patch[component_mask] = source_crop[component_mask]
    output_path = output_dir / _patch_filename("foreground", crop, ".nii.gz")
    write_nifti_patch(foreground, patch, crop.buffered_bbox, output_path)
    return output_path


def _write_raw_nifti_patch(source: LoadedNifti, crop: ComponentCrop, output_dir: Path, prefix: str) -> Path:
    patch = source.data[crop.buffered_bbox]
    output_path = output_dir / _patch_filename(prefix, crop, ".nii.gz")
    write_nifti_patch(source, patch, crop.buffered_bbox, output_path)
    return output_path


def _node_in_crop(vertex: ig.Vertex, attrs: set[str], crop: ComponentCrop) -> bool:
    if _graph_component_label(vertex, attrs) != crop.label:
        return False
    voxel_pos = _load_json_point(vertex["voxel_pos"], label=f"node {vertex.index} voxel_pos")
    bbox = crop.buffered_bbox
    return bool(
        int(bbox[0].start or 0) <= voxel_pos[0] < int(bbox[0].stop or 0)
        and int(bbox[1].start or 0) <= voxel_pos[1] < int(bbox[1].stop or 0)
        and int(bbox[2].start or 0) <= voxel_pos[2] < int(bbox[2].stop or 0)
    )


def crop_graph(graph: ig.Graph, crop: ComponentCrop, *, graph_label: str) -> ig.Graph:
    vertex_attrs = set(graph.vs.attributes())
    if "voxel_pos" not in vertex_attrs:
        raise ValueError(f"{graph_label} must contain node attribute 'voxel_pos'.")
    if "component_label" not in vertex_attrs:
        raise ValueError(f"{graph_label} must contain node attribute 'component_label' for component-filtered crops.")

    keep_indices = [vertex.index for vertex in graph.vs if _node_in_crop(vertex, vertex_attrs, crop)]
    index_map = {old_index: new_index for new_index, old_index in enumerate(keep_indices)}
    cropped = ig.Graph(directed=graph.is_directed())
    cropped.add_vertices(len(keep_indices))

    attrs = graph.vs.attributes()
    for new_index, old_index in enumerate(keep_indices):
        source_vertex = graph.vs[old_index]
        target_vertex = cropped.vs[new_index]
        for attr in attrs:
            target_vertex[attr] = source_vertex[attr]

    edge_pairs = []
    kept_edge_indices = []
    for edge in graph.es:
        if edge.source in index_map and edge.target in index_map:
            edge_pairs.append((index_map[edge.source], index_map[edge.target]))
            kept_edge_indices.append(edge.index)

    if edge_pairs:
        cropped.add_edges(edge_pairs)
        edge_attrs = graph.es.attributes()
        for target_edge, old_edge_index in zip(cropped.es, kept_edge_indices, strict=True):
            source_edge = graph.es[old_edge_index]
            for attr in edge_attrs:
                target_edge[attr] = source_edge[attr]

    return cropped


def write_graph_patch(graph: ig.Graph, crop: ComponentCrop, output_dir: Path, prefix: str, *, graph_label: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    cropped = crop_graph(graph, crop, graph_label=graph_label)
    output_path = output_dir / _patch_filename(prefix, crop, ".graphml")
    cropped.write_graphml(str(output_path))
    return output_path


def validate_matching_shape(source: LoadedNifti, foreground: LoadedNifti, *, label: str) -> None:
    if source.data.shape != foreground.data.shape:
        raise ValueError(
            f"{label} shape must match --input-fore shape. "
            f"Got {source.data.shape}, expected {foreground.data.shape}."
        )


def main() -> int:
    args = parse_args()
    foreground = load_nifti(args.input_fore, label="--input-fore")
    binary_foreground = foreground.data > 0
    labeled, objects = label_foreground(binary_foreground)
    component_count = int(len([item for item in objects if item is not None]))

    graph = load_graph(args.input_graph, label="--input-graph")
    result = check_graph_nodes(graph, binary_foreground, labeled)
    total_nodes = graph.vcount()
    escaping_count = total_nodes - result.inside_count

    print(f"total_graph_nodes={total_nodes}")
    print(f"foreground_connected_components={component_count}")

    if escaping_count == 0:
        print("all_graph_nodes_confined_within_foreground=true")
        return 0

    affected_labels = sorted(result.escaping_by_component)
    print("all_graph_nodes_confined_within_foreground=false")
    print(f"nodes_inside_foreground={result.inside_count}")
    print(f"escaping_nodes={escaping_count}")
    print(f"components_with_escaping_nodes={len(affected_labels)}")
    print("escaping_component_labels=" + ",".join(str(label) for label in affected_labels))

    output_nifti_dir = Path(args.nif_path).expanduser()
    output_graph_dir = Path(args.grapa_path).expanduser()
    output_nifti_dir.mkdir(parents=True, exist_ok=True)
    output_graph_dir.mkdir(parents=True, exist_ok=True)

    optional_niftis: list[tuple[str, LoadedNifti]] = []
    if args.input_img:
        image = load_nifti(args.input_img, label="--input-img")
        validate_matching_shape(image, foreground, label="--input-img")
        optional_niftis.append(("image", image))
    if args.input_skel:
        skeleton = load_nifti(args.input_skel, label="--input-skel")
        validate_matching_shape(skeleton, foreground, label="--input-skel")
        optional_niftis.append(("skeleton", skeleton))

    optional_graphs: list[tuple[str, ig.Graph, str]] = [("graph", graph, "--input-graph")]
    if args.input_graph2:
        optional_graphs.append(("graph2", load_graph(args.input_graph2, label="--input-graph2"), "--input-graph2"))

    crops = _component_crops(affected_labels, objects, foreground.data.shape, result.escaping_by_component)
    foreground_outputs = []
    raw_nifti_outputs = []
    graph_outputs = []
    for crop in crops:
        foreground_outputs.append(_write_foreground_patch(foreground, labeled, crop, output_nifti_dir))
        for prefix, source in optional_niftis:
            raw_nifti_outputs.append(_write_raw_nifti_patch(source, crop, output_nifti_dir, prefix))
        for prefix, source_graph, graph_label in optional_graphs:
            graph_outputs.append(write_graph_patch(source_graph, crop, output_graph_dir, prefix, graph_label=graph_label))

    print(f"foreground_patches_written={len(foreground_outputs)}")
    if optional_niftis:
        print(f"optional_nifti_patches_written={len(raw_nifti_outputs)}")
    print(f"graph_patches_written={len(graph_outputs)}")
    print(f"nifti_output_dir={output_nifti_dir}")
    print(f"graph_output_dir={output_graph_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
