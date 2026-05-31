"""CLI parser coverage for SkelHub framework commands."""

from __future__ import annotations

import pytest

from skelhub.cli.main import build_parser, main


BACKEND_FLAGS = (
    "--speed_param",
    "--threshold-scale",
    "--l1-sample-count",
    "--pk-mode",
    "--flux-threshold",
)


def _run_help(argv: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    with pytest.raises(SystemExit) as exc_info:
        main(argv)
    assert exc_info.value.code == 0
    return capsys.readouterr().out


def test_run_help_shows_only_common_options(capsys: pytest.CaptureFixture[str]) -> None:
    help_text = _run_help(["run", "--help"], capsys)

    assert "--algorithm" in help_text
    assert "--input" in help_text
    assert "--output" in help_text
    assert "--verbose" in help_text
    for flag in BACKEND_FLAGS:
        assert flag not in help_text


def test_laplacian_help_shows_only_laplacian_options(capsys: pytest.CaptureFixture[str]) -> None:
    help_text = _run_help(["run", "--algorithm", "laplacian", "--help"], capsys)

    assert "--speed_param" in help_text
    assert "--graph_output" in help_text
    assert "--graph-output" in help_text
    assert "--threshold-scale" not in help_text
    assert "--l1-sample-count" not in help_text
    assert "--pk-mode" not in help_text
    assert "--flux-threshold" not in help_text


def test_mcp_help_shows_only_mcp_options(capsys: pytest.CaptureFixture[str]) -> None:
    help_text = _run_help(["run", "--algorithm", "mcp", "--help"], capsys)

    assert "--threshold-scale" in help_text
    assert "--max-iterations" in help_text
    assert "--max-iteration" in help_text
    assert "--speed_param" not in help_text
    assert "--l1-sample-count" not in help_text
    assert "--pk-mode" not in help_text
    assert "--flux-threshold" not in help_text


def test_lee94_help_shows_only_lee94_options(capsys: pytest.CaptureFixture[str]) -> None:
    help_text = _run_help(["run", "--algorithm", "lee94", "--help"], capsys)

    assert "--binarize-threshold" in help_text
    assert "--threshold-scale" not in help_text
    assert "--speed_param" not in help_text
    assert "--l1-sample-count" not in help_text
    assert "--pk-mode" not in help_text
    assert "--flux-threshold" not in help_text


def test_wrong_backend_option_is_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "run",
                "--algorithm",
                "lee94",
                "-i",
                "input.nii.gz",
                "-o",
                "output.nii.gz",
                "--threshold-scale",
                "1.0",
            ]
        )

    assert exc_info.value.code == 2
    assert "unrecognized arguments: --threshold-scale 1.0" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("algorithm", "expected"),
    [
        ("flux", {"flux_threshold": 0.0, "flux_sigma": 0.5, "flux_sigma_unit": "physical"}),
        (
            "l1_skeleton",
            {
                "l1_sample_count": 512,
                "l1_initial_radius": None,
                "l1_radius_growth": 1.5,
                "l1_max_radius": None,
                "l1_max_iterations": 80,
                "l1_stop_error": 0.01,
                "l1_repulsion_mu": 0.35,
                "l1_repulsion_mu_min": 0.15,
                "l1_random_seed": 0,
                "l1_output_mode": "branches",
                "l1_use_density_weighting": True,
                "l1_use_recentering": True,
            },
        ),
        (
            "laplacian",
            {
                "graph_output": None,
                "graph_original": None,
                "speed_param": 0.05,
                "dist_param": 0.5,
                "med_param": 0.5,
                "degree_threshold": 5.0,
                "sampling": 1.0,
                "clustering_r": 1.0,
                "stop_param": 0.001,
                "n_free_iteration": 0,
                "area_param": 50.0,
                "poly_param": 10,
            },
        ),
        ("lee94", {"binarize_threshold": 0.5}),
        (
            "mcp",
            {
                "root_method": "max_fdt",
                "threshold_scale": 1.0,
                "dilation_factor": 2.0,
                "max_iterations": 200,
                "min_object_size": 50,
                "label_objects": False,
            },
        ),
        (
            "palagyi_kuba",
            {"pk_mode": "curve", "pk_binarize_threshold": 0.5, "pk_max_cycles": None},
        ),
    ],
)
def test_minimal_run_parse_preserves_backend_defaults(algorithm: str, expected: dict[str, object]) -> None:
    parser = build_parser(run_algorithm=algorithm)
    args = parser.parse_args(["run", "--algorithm", algorithm, "-i", "input.nii.gz", "-o", "output.nii.gz"])

    assert args.command == "run"
    assert args.algorithm == algorithm
    assert args.input == "input.nii.gz"
    assert args.output == "output.nii.gz"
    assert args.verbose is False
    for name, value in expected.items():
        assert getattr(args, name) == value

