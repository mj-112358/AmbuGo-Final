#!/usr/bin/env python3
"""Verify retained evidence and run bounded reproducibility checks.

Install requirements-checks.txt. Simulation tests execute in temporary copies
and separate Python processes. Checks cover frozen source integrity, paired
records, accounting identities and numerical reference cases."""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "work" / "v9"
MODEL_SHA256 = "471a22911a2de9773fcd839872b3ba1ec5e00412c0ecc79142503e72f41cecf2"
INITIAL_SHA256 = "44cedf73590afaef3bf7cf3350b78e5736e33a120309db506d111af93065de30"
CONFIG_SHA256 = "d6dddff77a9fa619589a2f197007ceede0fd189bd23927e98ea744d17ce698f0"
FIXTURES = ("nodes.csv", "edges.csv", "vehicle_classes.csv", "od_probabilities.csv")
EVALUATION_PHASES = ("main", "sensitivity", "ablation", "adaptive_base", "exact_counts")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_inputs() -> dict:
    frozen = read_json(STUDY / "sumo_frozen_source.json")
    require(frozen["sha256"] == MODEL_SHA256, "Frozen model record changed")
    require(frozen["initial_sha256"] == INITIAL_SHA256, "Initial model record changed")
    for name, expected in (("sumo_study.py", MODEL_SHA256),
                           ("sumo_study_initial.py", INITIAL_SHA256)):
        require(sha256(STUDY / name) == expected, f"Frozen source changed: {name}")
    selected = read_json(STUDY / "selected_policy.json")
    config = selected["selected_configuration"]
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    require(hashlib.sha256(encoded).hexdigest() == CONFIG_SHA256,
            "Frozen selected configuration changed")
    require(selected["model_sha256"] == MODEL_SHA256, "Selected policy model mismatch")
    for name in FIXTURES:
        require((ROOT / "outputs" / "AmbuGo_v7_Synthetic_Data" / name).is_file(),
                f"Missing required fixture: {name}")
    print("PASS frozen model sources, selected configuration, and required fixtures")
    return config


def phase_spec(phase: str) -> tuple:
    if phase == "main":
        return range(48), (0.6, 0.8, 0.95), (1, 4, 10), ("P0", "P1", "P2", "P3")
    if phase in ("sensitivity", "adaptive_base", "exact_counts"):
        return range(12), (0.6, 0.95), (4,), ("P0", "P2", "P3")
    if phase == "ablation":
        return range(12), (0.6, 0.95), (4,), ("P0", "P3_no_progress")
    if phase == "train":
        labels = [f"P3_b{b}_e{e}_{mode}" for b in (600, 2400, 10000)
                  for e in (0, 10) for mode in ("multi", "strong")]
    else:
        labels = [f"P3_b{b}_g{g}" for b in (600, 2400, 10000) for g in (5, 10, 20)]
    return range(5001, 5007), (0.7, 0.9), (4,), ("P0", "P2", *labels)


def close(actual: float, expected: float, message: str) -> None:
    require(math.isfinite(actual) and math.isfinite(expected)
            and math.isclose(actual, expected, rel_tol=0, abs_tol=1e-8), message)


def microscopic_records(selected: dict) -> None:
    total = 0
    main_schedules = {}
    for phase in (*EVALUATION_PHASES, "train", "train_progress"):
        folder = STUDY / ("sumo_" + phase)
        protocol = read_json(folder / "protocol.json")
        records = read_json(folder / "records.json")
        summary = read_json(folder / "run_summary.json")
        seeds, loads, missions, labels = phase_spec(phase)
        expected = set(itertools.product(seeds, loads, missions, labels))
        require(protocol["seeds"] == list(seeds), f"{phase}: seed grid changed")
        require(protocol["loads"] == list(loads), f"{phase}: load grid changed")
        require(protocol["missions_per_hour"] == list(missions), f"{phase}: dose grid changed")
        require(protocol["expected_runs"] == len(expected) == len(records)
                == summary["actual_runs"], f"{phase}: incomplete run count")
        require(not (folder / "failure.json").exists(), f"{phase}: unresolved failure record")
        expected_hash = INITIAL_SHA256 if phase == "train" else MODEL_SHA256
        require(protocol["model_sha256"] == expected_hash, f"{phase}: model hash mismatch")
        configurations = {c["label"]: c for c in protocol["configurations"]}
        require(set(configurations) == set(labels), f"{phase}: configuration labels changed")
        require(len(configurations) == len(protocol["configurations"]),
                f"{phase}: duplicate configuration label")
        by_key = {(r["seed"], r["load"], r["missions"], r["label"]): r for r in records}
        require(len(by_key) == len(records) and set(by_key) == expected,
                f"{phase}: duplicate, missing, or unexpected condition")
        for seed, load, count in itertools.product(seeds, loads, missions):
            group = [by_key[seed, load, count, label] for label in labels]
            baseline = group[0]
            schedule = baseline["schedule_sha256"]
            mission_cohort = [(a["id"], a["dispatch"], a["origin"])
                              for a in baseline["mission_rows"]]
            require(len(mission_cohort) == count, f"{phase}: mission count mismatch")
            if phase == "main":
                main_schedules[seed, load, count] = schedule
            elif phase in EVALUATION_PHASES:
                require(schedule == main_schedules[seed, load, count],
                        f"{phase}: scenario differs from matching main condition")
            for row in group:
                context = f"{phase}/{seed}/{load}/{count}/{row['label']}"
                require(row["schedule_sha256"] == schedule, f"{context}: unpaired schedule")
                require(row["n_ordinary"] == baseline["n_ordinary"],
                        f"{context}: unpaired ordinary cohort")
                require([(a["id"], a["dispatch"], a["origin"])
                         for a in row["mission_rows"]] == mission_cohort,
                        f"{context}: unpaired mission cohort")
                config = configurations[row["label"]]
                require(row["policy"] == config["policy"], f"{context}: policy mismatch")
                for key, value in protocol["common"].items():
                    require(row["config"][key] == value, f"{context}: common setting {key}")
                for key, value in config.items():
                    if key not in ("label", "policy"):
                        require(row["config"][key] == value, f"{context}: setting {key}")
                if phase in EVALUATION_PHASES and row["policy"] == "P3":
                    for key, value in selected.items():
                        target = None if phase == "ablation" and key == "progress_guard_s" else value
                        require(row["config"][key] == target,
                                f"{context}: frozen selected setting {key}")
                for field in ("partition_identity_max_error", "residence_identity_error"):
                    close(row[field], 0, f"{context}: {field}")
                close(row["ordinary_J_vehicle_s"], row["ordinary_individual_J_vehicle_s"],
                      f"{context}: population/individual residence mismatch")
                close(row["delta_residence_vehicle_s"],
                      row["positive_spatial_vehicle_s"] - row["negative_spatial_vehicle_s"],
                      f"{context}: spatial decomposition mismatch")
                close(row["delta_residence_vehicle_s"],
                      row["ordinary_J_vehicle_s"] - baseline["ordinary_J_vehicle_s"],
                      f"{context}: baseline residence mismatch")
                if phase in EVALUATION_PHASES:
                    close(row["delta_residence_vehicle_s"],
                          row["positive_individual_residence_vehicle_s"]
                          - row["negative_individual_residence_vehicle_s"],
                          f"{context}: individual decomposition mismatch")
        total += len(records)
        print(f"PASS {phase}: {len(records)} complete, paired microscopic records")
    require(total == 2292, "Unexpected microscopic evaluation/development total")


def mesoscopic_records() -> None:
    expected = set(itertools.product((0.6, 0.7, 0.8, 0.85, 0.9, 0.95),
                                    (0.0, 0.5), range(200),
                                    ("P0", "P1", "P2", "P3", "P3C", "P4")))
    for branch in (Path("teammate_v8/ambugo_v8"), Path("v8_corrected")):
        with (STUDY / branch / "results/eval_runs.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        keys = {(float(r["X"]), float(r["rho"]), int(r["rep"]), r["policy"]) for r in rows}
        require(len(rows) == len(keys) == 14400 and keys == expected,
                f"{branch}: incomplete or duplicated mesoscopic grid")
        print(f"PASS {branch}: 14,400 unique mesoscopic records")


def copy_model(source: Path, destination: Path) -> None:
    for name in ("ambugo", "tests", "scripts", "geometry"):
        shutil.copytree(source / name, destination / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    (destination / "results").mkdir()


def run_test(label: str, command: list[str], cwd: Path, environment: dict) -> str:
    started = time.perf_counter()
    result = subprocess.run([sys.executable, *command], cwd=cwd, env=environment,
                            text=True, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f"{label} failed (exit {result.returncode})\n"
                           + result.stdout[-12000:] + result.stderr[-12000:])
    print(f"PASS {label} ({time.perf_counter() - started:.2f} s)")
    return result.stdout


def isolated_tests() -> None:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    # Preserve an explicitly supplied local dependency path across cwd changes.
    if environment.get("PYTHONPATH"):
        environment["PYTHONPATH"] = os.pathsep.join(
            str(Path(part or ".").resolve())
            for part in environment["PYTHONPATH"].split(os.pathsep))
    with tempfile.TemporaryDirectory(prefix="ambugo_checks_") as directory:
        temp = Path(directory)
        study = temp / "work/v9"
        study.mkdir(parents=True)
        for name in ("analysis.py", "meso.py", "meso_checks.py"):
            shutil.copy2(STUDY / name, study / name)
        fixture = temp / "outputs/AmbuGo_v7_Synthetic_Data"
        fixture.mkdir(parents=True)
        for name in FIXTURES:
            shutil.copy2(ROOT / "outputs/AmbuGo_v7_Synthetic_Data" / name, fixture / name)
        stdout = run_test("5 statistical utility checks",
                          [str(study / "analysis.py"), "--self-check"], temp, environment)
        require(json.loads(stdout)["checks_passed"] == 5, "Statistical check count changed")
        for branch in (Path("teammate_v8/ambugo_v8"), Path("v8_corrected")):
            copy_model(STUDY / branch, study / branch)
        original = study / "teammate_v8/ambugo_v8"
        run_test("8 original-source checks", [str(original / "tests/run_tests.py")],
                 temp, environment)
        report = read_json(original / "results/verification.json")
        checks = [value for value in report.values() if isinstance(value, dict)]
        require(len(checks) == 8 and all(value["passed"] for value in checks),
                "Original test report is incomplete")
        corrected = study / "v8_corrected"
        run_test("18 mechanical correction checks",
                 [str(corrected / "tests/mechanical_checks.py")], temp, environment)
        report = read_json(corrected / "results/mechanical_verification.json")
        require(report["checks_passed"] == 18 and len(report["checks"]) == 18
                and all(value["passed"] for value in report["checks"]),
                "Mechanical correction test report is incomplete")
        report_path = temp / "meso_verification.json"
        run_test("24 independent reference checks",
                 [str(study / "meso_checks.py"), "--out", str(report_path)], temp, environment)
        report = read_json(report_path)
        require(report["checks_passed"] == 24 and len(report["checks"]) == 24
                and all(value["passed"] for value in report["checks"]),
                "Independent reference test report is incomplete")


def main() -> int:
    started = time.perf_counter()
    try:
        selected = frozen_inputs()
        microscopic_records(selected)
        mesoscopic_records()
        isolated_tests()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    print(f"All checks passed in {time.perf_counter() - started:.2f} s.")
    print("Verification completed using retained records and isolated numerical tests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
