"""Input, coordinate and tolerance validation for voxel-based skeleton evaluation.

Every physical quantity is normalized to micrometres here, so the metric code
only ever sees boolean arrays, per-axis spacing in µm and tolerances in µm.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from typing import Sequence

import nibabel as nib
import numpy as np

from skelhub.core import VolumeData


SUPPORTED_RADIUS_UNITS = ("voxels", "um")
# Accepted spatial-unit names and their canonical form; nibabel reports micrometres as "micron".
CANONICAL_SPATIAL_UNITS = {"meter": "meter", "mm": "mm", "um": "um", "micron": "um"}
SPATIAL_UNIT_TO_UM = {"meter": 1_000_000.0, "mm": 1_000.0, "um": 1.0}
UNKNOWN_SPATIAL_UNITS = ("unknown", "")
# NIfTI xyzt_units spatial codes (low three bits); the time unit is irrelevant here.
_NIFTI_SPATIAL_CODES = {0: "unknown", 1: "meter", 2: "mm", 3: "micron"}

# Largest |cos angle| between voxel axes still treated as orthogonal.
SHEAR_TOLERANCE = 1e-5
# Relative slack absorbing float32 header rounding (0.05 mm is stored as 0.0500000007 mm).
RELATIVE_TOLERANCE = 1e-5
# Prediction and reference affines (in µm) may differ by this fraction of the smallest voxel spacing.
AFFINE_MATCH_FRACTION = 1e-3


@dataclass(slots=True)
class ResolvedSpatialUnit:
    """The unit used to interpret stored spacing/affine values, and where it came from.

    ``header_unit`` is what the header said (``None`` when there is no header,
    as for in-memory arrays). ``source`` is ``header`` or ``user``.
    """

    header_unit: str | None
    effective_unit: str
    source: str
    warning: str | None = None


@dataclass(slots=True)
class SkeletonVolumeInput:
    """Validated binary skeleton volume with its physical frame in micrometres."""

    data: np.ndarray
    affine_um: np.ndarray
    spacing_um: tuple[float, float, float]
    units: ResolvedSpatialUnit
    label: str
    path: str | None = None

    @property
    def spatial_unit(self) -> str:
        """Effective (canonical) spatial unit."""
        return self.units.effective_unit


@dataclass(slots=True)
class RawSkeletonNifti:
    """A NIfTI read from disk but not yet validated or unit-resolved."""

    data: np.ndarray
    affine: np.ndarray
    header_unit: str
    header_spacing: tuple[float, float, float]
    path: str


@dataclass(slots=True)
class ToleranceSpec:
    """One requested geometry tolerance and its physical value in micrometres."""

    requested_value: float
    requested_unit: str
    tolerance_um: float
    is_primary: bool


def header_spatial_unit(header: object) -> str:
    """Spatial-unit label of a NIfTI header, ``unknown`` when there is no header.

    nibabel's ``get_xyzt_units`` raises ``KeyError`` for undefined unit codes,
    including undefined time codes. This reads the spatial bits only and
    returns ``unrecognized code N`` for undefined ones, which
    :func:`resolve_spatial_unit` then rejects.
    """
    if header is None:
        return "unknown"
    try:
        code = int(np.asarray(header["xyzt_units"]).item()) & 0x07
    except (KeyError, TypeError, ValueError, IndexError):
        if not hasattr(header, "get_xyzt_units"):
            return "unknown"
        return header.get_xyzt_units()[0] or "unknown"
    return _NIFTI_SPATIAL_CODES.get(code, f"unrecognized code {code}")


def resolve_spatial_unit(
    header_unit: str | None,
    supplied_unit: str | None,
    *,
    label: str,
    role: str | None = None,
    stored_spacing: Sequence[float] | None = None,
) -> ResolvedSpatialUnit:
    """Decide which unit labels the stored spacing and affine values.

    - Known header unit: used as is; a supplied unit must be equivalent.
    - Unknown header unit: the supplied unit is used and a warning is recorded.
    - No header (``header_unit=None``): the supplied unit is required, without a warning.

    A supplied unit only labels the stored numbers; it never rescales them.
    ``role`` (``pred`` or ``ref``) names the CLI flag in messages.
    """
    flag = f"--{role}-spatial-unit" if role else "a spatial unit"
    supplied = None
    if supplied_unit is not None:
        supplied = CANONICAL_SPATIAL_UNITS.get(str(supplied_unit))
        if supplied is None:
            raise ValueError(
                f"Unsupported spatial unit '{supplied_unit}' supplied for {label}. "
                f"Expected one of {sorted(CANONICAL_SPATIAL_UNITS)}."
            )

    if header_unit is None:
        if supplied is None:
            raise ValueError(f"{label} needs a spatial unit, one of {sorted(CANONICAL_SPATIAL_UNITS)}.")
        return ResolvedSpatialUnit(header_unit=None, effective_unit=supplied, source="user")

    if header_unit in UNKNOWN_SPATIAL_UNITS:
        if supplied is None:
            hint = (
                f"Supply {flag} mm or {flag} um (Python: {role}_spatial_unit=...)"
                if role
                else "Supply a spatial unit"
            )
            raise ValueError(
                f"{label} has unknown spatial units. {hint} using the unit of the stored spacing and "
                "affine values. SkelHub does not guess units."
            )
        spacing_text = ""
        if stored_spacing is not None:
            spacing_um = ", ".join(
                f"{float(value) * unit_factor_to_um(supplied):.6g}" for value in stored_spacing[:3]
            )
            spacing_text = f" Effective spacing: ({spacing_um}) um."
        warning = (
            f"{label} spatial unit was unknown; interpreting the stored coordinates as {supplied} "
            f"from {flag if role else 'the supplied unit'}.{spacing_text} The input was not modified."
        )
        return ResolvedSpatialUnit(header_unit=header_unit, effective_unit=supplied, source="user", warning=warning)

    known = CANONICAL_SPATIAL_UNITS.get(header_unit)
    if known is None:
        raise ValueError(
            f"{label} header has unsupported spatial unit '{header_unit}'. "
            f"Supported: {sorted(CANONICAL_SPATIAL_UNITS)}."
        )
    if supplied is not None and supplied != known:
        raise ValueError(
            f"{label} header declares '{header_unit}', which conflicts with the supplied unit "
            f"'{supplied_unit}'. A supplied unit only fills in unknown headers; it never overrides a known one."
        )
    return ResolvedSpatialUnit(header_unit=header_unit, effective_unit=known, source="header")


def unit_factor_to_um(unit: str) -> float:
    """Micrometres per stored coordinate unit, for any accepted unit name."""
    return SPATIAL_UNIT_TO_UM[CANONICAL_SPATIAL_UNITS[unit]]


def prepare_skeleton_volume(
    data: np.ndarray,
    affine: np.ndarray,
    header_unit: str | None,
    *,
    label: str,
    supplied_unit: str | None = None,
    role: str | None = None,
    path: str | None = None,
    header_spacing: Sequence[float] | None = None,
) -> SkeletonVolumeInput:
    """Validate a 3D binary skeleton and its voxel-to-world frame.

    ``affine`` and ``header_spacing`` (NIfTI zooms) are stored values whose unit
    is resolved by :func:`resolve_spatial_unit`; both are scaled by the same
    factor (linear part and translation, not the homogeneous row) and must
    then agree. Inputs are never modified.
    """
    array = np.asarray(data)
    if array.ndim != 3:
        raise ValueError(f"{label} must be a 3D volume. Got ndim={array.ndim} with shape {array.shape}.")
    if array.size == 0:
        raise ValueError(f"{label} has no voxels (shape {array.shape}).")
    _require_binary(array, label=label)

    affine_um = _validated_affine(affine, label=label)
    units = resolve_spatial_unit(
        header_unit,
        supplied_unit,
        label=label,
        role=role,
        stored_spacing=np.linalg.norm(affine_um[:3, :3], axis=0),
    )
    factor = unit_factor_to_um(units.effective_unit)
    affine_um[:3] *= factor
    spacing_um = _orthogonal_spacing(affine_um, label=label)

    if header_spacing is not None:
        header_um = np.asarray([float(value) for value in header_spacing[:3]]) * factor
        if not np.allclose(header_um, spacing_um, rtol=RELATIVE_TOLERANCE, atol=0.0):
            raise ValueError(
                f"{label} header spacing {tuple(header_um.round(6))} um disagrees with the affine "
                f"column lengths {tuple(np.round(spacing_um, 6))} um. Fix the NIfTI header so "
                "pixdim and the sform/qform describe the same grid."
            )

    return SkeletonVolumeInput(
        data=array != 0,
        affine_um=affine_um,
        spacing_um=spacing_um,
        units=units,
        label=label,
        path=path,
    )


def read_skeleton_nifti(path: str | Path, *, label: str) -> RawSkeletonNifti:
    """Read a NIfTI's voxels, affine, header unit and zooms without validating them."""
    volume_path = Path(path)
    if not volume_path.exists():
        raise FileNotFoundError(f"{label} does not exist: {volume_path}")
    if not str(volume_path).endswith((".nii", ".nii.gz")):
        raise ValueError(f"{label} must be a .nii or .nii.gz file. Got: {volume_path}")

    image = nib.load(str(volume_path))
    if not isinstance(image, nib.Nifti1Image):
        image = nib.Nifti1Image.from_image(image)
    return RawSkeletonNifti(
        data=np.asarray(image.dataobj),
        affine=np.array(image.affine, dtype=float),
        header_unit=header_spatial_unit(image.header),
        header_spacing=tuple(float(value) for value in image.header.get_zooms()[:3]),
        path=str(volume_path),
    )


def prepare_skeleton_nifti(
    raw: RawSkeletonNifti,
    *,
    label: str,
    supplied_unit: str | None = None,
    role: str | None = None,
) -> SkeletonVolumeInput:
    """Validate a NIfTI read by :func:`read_skeleton_nifti`."""
    return prepare_skeleton_volume(
        raw.data,
        raw.affine,
        raw.header_unit,
        label=label,
        supplied_unit=supplied_unit,
        role=role,
        path=raw.path,
        header_spacing=raw.header_spacing,
    )


def load_skeleton_nifti(
    path: str | Path,
    *,
    label: str,
    supplied_unit: str | None = None,
    role: str | None = None,
) -> SkeletonVolumeInput:
    """Load and validate a raw binary skeleton NIfTI without implicit normalization."""
    raw = read_skeleton_nifti(path, label=label)
    return prepare_skeleton_nifti(raw, label=label, supplied_unit=supplied_unit, role=role)


def volume_input_from_volume_data(
    volume: VolumeData,
    *,
    label: str,
    data: np.ndarray | None = None,
    supplied_unit: str | None = None,
    role: str | None = None,
) -> SkeletonVolumeInput:
    """Validate a ``VolumeData`` (or ``data`` on its grid) using its affine and header units.

    A missing header counts as unknown units, so ``supplied_unit`` is then required.
    """
    header_unit = header_spatial_unit(volume.header)
    values = volume.data if data is None else data
    if data is not None and np.shape(data) != np.shape(volume.data):
        raise ValueError(
            f"{label} shape {np.shape(data)} does not match its input volume shape {np.shape(volume.data)}."
        )
    return prepare_skeleton_volume(
        values,
        volume.affine,
        header_unit,
        label=label,
        supplied_unit=supplied_unit,
        role=role,
        path=volume.path,
        header_spacing=volume.spacing,
    )


def require_matching_shapes(pred_shape: Sequence[int], ref_shape: Sequence[int]) -> None:
    """Fail early when prediction and reference voxel grids differ in shape."""
    if tuple(pred_shape) != tuple(ref_shape):
        raise ValueError(
            "Prediction and reference skeletons must have matching shapes. "
            f"Got pred={tuple(pred_shape)}, ref={tuple(ref_shape)}."
        )


def array_affine(
    spacing: Sequence[float],
    affine: np.ndarray | None,
) -> np.ndarray:
    """Return the affine for in-memory arrays: ``diag(spacing)`` or a checked explicit affine."""
    normalized = _normalize_spacing(spacing)
    if affine is None:
        return np.diag([*normalized, 1.0])
    matrix = np.asarray(affine, dtype=float)
    if matrix.shape == (4, 4) and np.isfinite(matrix).all():
        columns = np.linalg.norm(matrix[:3, :3], axis=0)
        if not np.allclose(columns, normalized, rtol=RELATIVE_TOLERANCE, atol=0.0):
            raise ValueError(
                f"spacing {normalized} does not match the affine column lengths {tuple(columns.round(9))}."
            )
    return matrix


def validate_matching_inputs(pred: SkeletonVolumeInput, ref: SkeletonVolumeInput) -> None:
    """Require the same voxel grid and the same physical voxel-to-world transform."""
    require_matching_shapes(pred.data.shape, ref.data.shape)

    tolerance = AFFINE_MATCH_FRACTION * min(min(pred.spacing_um), min(ref.spacing_um))
    difference = np.abs(pred.affine_um[:3] - ref.affine_um[:3])
    if float(difference.max()) > tolerance:
        linear_diff = float(difference[:, :3].max())
        origin_diff = pred.affine_um[:3, 3] - ref.affine_um[:3, 3]
        raise ValueError(
            "Prediction and reference skeletons are not on the same physical grid "
            f"(affines compared in um, tolerance {tolerance:.3g} um). "
            f"Origin difference pred-ref: {tuple(np.round(origin_diff, 6))} um; "
            f"largest spacing/orientation entry difference: {linear_diff:.6g} um. "
            f"Prediction units '{pred.units.effective_unit}' (from {pred.units.source}), "
            f"reference units '{ref.units.effective_unit}' (from {ref.units.source}). "
            "SkelHub does not register or resample; align the inputs first."
        )


def normalize_tolerances(
    buffer_radius: float | Sequence[float],
    unit: str,
    spacing_um: tuple[float, float, float],
) -> list[ToleranceSpec]:
    """Validate requested tolerances and convert them to micrometres, preserving order.

    A single number and a sequence go through the same path. The first value is
    primary. Voxel radii are only accepted on isotropic grids.
    """
    if unit not in SUPPORTED_RADIUS_UNITS:
        raise ValueError(
            f"Unsupported buffer radius unit '{unit}'. Expected one of {list(SUPPORTED_RADIUS_UNITS)}."
        )
    values = _radius_values(buffer_radius)
    if len(set(values)) != len(values):
        raise ValueError(f"Buffer radii must be distinct; got {values}.")

    if unit == "um":
        scale = 1.0
    else:
        if not np.allclose(spacing_um, spacing_um[0], rtol=RELATIVE_TOLERANCE, atol=0.0):
            raise ValueError(
                f"Voxel-unit buffer radii are ambiguous on anisotropic grids (spacing {spacing_um} um). "
                "Give the tolerance in micrometres with --buffer-radius-unit um."
            )
        scale = float(np.mean(spacing_um))

    return [
        ToleranceSpec(
            requested_value=value,
            requested_unit=unit,
            tolerance_um=value * scale,
            is_primary=index == 0,
        )
        for index, value in enumerate(values)
    ]


def _radius_values(buffer_radius: float | Sequence[float]) -> list[float]:
    if isinstance(buffer_radius, (str, bytes)):
        raise ValueError(f"Buffer radius must be numeric; got {buffer_radius!r}.")
    raw = [buffer_radius] if isinstance(buffer_radius, Real) else list(buffer_radius)
    if not raw:
        raise ValueError("At least one buffer radius is required.")
    values: list[float] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, Real):
            raise ValueError(f"Buffer radius must be numeric; got {item!r}.")
        value = float(item)
        if not np.isfinite(value):
            raise ValueError(f"Buffer radius must be finite; got {value}.")
        if value < 0:
            raise ValueError(f"Buffer radius must be greater than or equal to 0; got {value}.")
        values.append(value)
    return values


def _require_binary(array: np.ndarray, *, label: str) -> None:
    if array.dtype == bool:
        return
    unique_values = np.unique(array)
    if not np.isin(unique_values, (0, 1)).all():
        preview = ", ".join(str(value) for value in unique_values[:10])
        if unique_values.size > 10:
            preview += ", ..."
        raise ValueError(f"{label} must contain only binary values {{0, 1}}. Found values: [{preview}]")


def _validated_affine(affine: np.ndarray, *, label: str) -> np.ndarray:
    matrix = np.array(affine, dtype=float, copy=True)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError(f"{label} affine must be a finite 4x4 matrix.")
    if not np.allclose(matrix[3], (0.0, 0.0, 0.0, 1.0)):
        raise ValueError(f"{label} affine bottom row must be [0, 0, 0, 1]; got {matrix[3].tolist()}.")
    return matrix


def _orthogonal_spacing(affine_um: np.ndarray, *, label: str) -> tuple[float, float, float]:
    linear = affine_um[:3, :3]
    spacing = np.linalg.norm(linear, axis=0)
    if np.any(spacing <= 0) or abs(np.linalg.det(linear)) <= 1e-12 * float(np.prod(spacing)):
        raise ValueError(f"{label} affine is singular; voxel spacing is undefined.")
    unit_axes = linear / spacing
    off_diagonal = np.abs((unit_axes.T @ unit_axes)[~np.eye(3, dtype=bool)])
    if float(off_diagonal.max()) > SHEAR_TOLERANCE:
        raise ValueError(
            f"{label} voxel grid is sheared (largest |cos angle| between voxel axes = "
            f"{float(off_diagonal.max()):.3g}). Distances use per-axis spacing, which is only exact "
            "on orthogonal grids. Resample the volume to an orthogonal grid first."
        )
    return tuple(float(value) for value in spacing)  # type: ignore[return-value]


def _normalize_spacing(spacing: Sequence[float]) -> tuple[float, float, float]:
    values = tuple(float(value) for value in spacing)
    if len(values) != 3:
        raise ValueError(f"spacing must contain exactly three values. Got {spacing}.")
    if any(not np.isfinite(value) or value <= 0 for value in values):
        raise ValueError(f"spacing must contain positive finite values. Got {values}.")
    return values  # type: ignore[return-value]
