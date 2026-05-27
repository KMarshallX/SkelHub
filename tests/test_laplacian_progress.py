from pathlib import Path

from skelhub.algorithms.laplacian import LaplacianConfig
from skelhub.algorithms.laplacian.progress import LaplacianProgress
from skelhub.api import run_algorithm_from_path


def test_laplacian_progress_remaining_time_counts_down(monkeypatch) -> None:
    messages: list[str] = []
    now = [1.0]
    monkeypatch.setattr("skelhub.algorithms.laplacian.progress.time.perf_counter", lambda: now[0])
    progress = LaplacianProgress(log=messages.append, stages=("one", "two", "three"), started=0.0)

    progress.start("one")
    progress.finish()
    now[0] = 2.0
    progress.start("two")

    assert "remaining~00:00:02" in messages[-2]
    assert "remaining~00:00:01" in messages[-1]


def test_laplacian_verbose_log_reports_progress_eta_and_current_stage(tmp_path: Path) -> None:
    messages: list[str] = []
    fixture = Path(__file__).parent / "fixtures" / "straight_tube.nii.gz"

    result = run_algorithm_from_path(
        algorithm="laplacian",
        input_path=fixture,
        output_path=tmp_path / "skeleton.nii.gz",
        config=LaplacianConfig(),
        log=messages.append,
    )

    report = "\n".join(messages)
    assert result.algorithm_name == "laplacian"
    assert "laplacian [" in report
    assert "remaining~" in report
    assert "stage=construct dense graph" in report
    assert "stage=contract graph" in report
    assert "iteration=" in report
    assert "cycle_area=" in report
    assert "(100%) stage=assemble result | complete" in report
