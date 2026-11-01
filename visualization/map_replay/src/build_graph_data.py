#!/usr/bin/env python3
"""Rebuild the two graph curves from raw SUMO replay arrays.

Apply the original build_story.py data selection to the fields used by the
final 20-second graph. Event annotations use the optional story and
controller files as their source."""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GRAPH_KEYS = ("t_s", "ambulance_speed_kmh", "ordinary_stopped_network",
              "routing_only_ordinary_stopped_network")
DEFINITIONS = {
    "ambulance_speed_kmh": "Recorded simulator speed; null when the ambulance is not present.",
    "ordinary_stopped_network": (
        "Ordinary vehicles physically present anywhere in the simulated network at "
        "speed below 0.1 m/s, including internal junction connectors. Excludes "
        "ambulances and not-yet-inserted source queues."),
    "routing_only_ordinary_stopped_network": (
        "The same stopped-vehicle definition in the matched routing-only control "
        "run. Same synthetic demand and all three missions."),
    "comparison_scope": (
        "Matched routing-only comparison across the shared network, including "
        "the combined traffic effects of all three ambulance missions."),
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_replay(directory, policy):
    """Read only the four arrays needed for speed and all-network counts."""
    array_path = directory / f"{policy}.npz"
    metadata_path = directory / f"{policy}.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    with np.load(array_path, allow_pickle=False) as archive:
        replay = {name: archive[name] for name in ("t", "offsets", "vehicle", "speed")}
    times, offsets = replay["t"], replay["offsets"]
    if len(offsets) != len(times) + 1 or offsets[0] != 0:
        raise ValueError(f"Invalid ragged replay offsets in {array_path.name}")
    if offsets[-1] != len(replay["vehicle"]) or len(replay["speed"]) != len(replay["vehicle"]):
        raise ValueError(f"Vehicle and speed records are inconsistent in {array_path.name}")
    if not np.all(np.diff(times) > 0) or np.any(np.diff(offsets.astype(np.int64)) < 0):
        raise ValueError(f"Non-monotone times or offsets in {array_path.name}")
    vehicles = metadata["vehicles"]
    if np.any(replay["vehicle"] < 0) or np.any(replay["vehicle"] >= len(vehicles)):
        raise ValueError(f"Unknown vehicle index in {array_path.name}")
    return replay, metadata


def sample_frames(replay):
    """Map each flat vehicle observation to its recorded half-second frame."""
    return np.repeat(np.arange(len(replay["t"]), dtype=np.int64),
                     np.diff(replay["offsets"]).astype(np.int64))


def ordinary_stopped_counts(replay, metadata, frame_indices):
    """Count ordinary stopped vehicles using each run's ambulance metadata."""
    ambulance_indices = [i for i, item in enumerate(metadata["vehicles"])
                         if item["type"] == "ambulance"]
    ordinary = ~np.isin(replay["vehicle"], ambulance_indices)
    # Classify recorded speeds using SUMO's 0.1 m/s halting threshold.
    stopped = ordinary & (replay["speed"] < 0.1)
    return np.bincount(frame_indices[stopped], minlength=len(replay["t"]))


def compare_curves(rebuilt, reference_path):
    """Compare the four graph-used arrays, ignoring unrelated legacy fields."""
    reference = json.loads(Path(reference_path).read_text(encoding="utf-8"))
    for key in GRAPH_KEYS:
        if rebuilt["recorded"][key] != reference["recorded"][key]:
            raise AssertionError(f"Rebuilt graph series differs from reference: {key}")
    return True


def build(replay_dir=None, output_path=None, focus_ambulance="a002"):
    """Regenerate data/progression_data.json and return its JSON-compatible data.

    Inputs are B1000's P3.npz/P3.json and the matched routing-only P0.npz/P0.json.
    Rebuilding the graph is distinct from rerunning the experiment in SUMO.
    """
    directory = Path(replay_dir) if replay_dir is not None else ROOT / "data" / "replays"
    output_path = Path(output_path) if output_path is not None else ROOT / "data" / "progression_data.json"
    replay, metadata = load_replay(directory, "P3")
    baseline, baseline_metadata = load_replay(directory, "P0")
    if metadata["configuration"]["harm_budget"] != 1000:
        raise ValueError("The frozen graph story requires the B1000 sensitivity run.")
    if not np.array_equal(replay["t"], baseline["t"]):
        raise ValueError("The paired replay clocks must match exactly.")
    for key in ("net_sha256", "schedule_sha256"):
        if metadata.get(key) != baseline_metadata.get(key):
            raise ValueError(f"Paired runs do not share {key}.")
    if metadata["seed"] != baseline_metadata["seed"]:
        raise ValueError("The paired runs must share the synthetic-demand seed.")

    focus_index = next(i for i, item in enumerate(metadata["vehicles"])
                       if item["id"] == focus_ambulance)
    mission = next(item for item in metadata["missions"] if item["id"] == focus_ambulance)
    frame_indices = sample_frames(replay)
    baseline_frame_indices = sample_frames(baseline)
    counts = ordinary_stopped_counts(replay, metadata, frame_indices)
    baseline_counts = ordinary_stopped_counts(baseline, baseline_metadata, baseline_frame_indices)
    speed = [None] * len(replay["t"])
    focus_observations = np.flatnonzero(replay["vehicle"] == focus_index)
    focus_frames = frame_indices[focus_observations]
    if len(np.unique(focus_frames)) != len(focus_frames):
        raise ValueError("More than one observation of the focused ambulance in a frame.")
    for record, frame in zip(focus_observations, focus_frames):
        # Preserve the original float32 multiplication and then JSON conversion.
        speed[int(frame)] = float(replay["speed"][record] * 3.6)

    selected = np.flatnonzero(replay["t"] >= mission["depart"])
    recorded = {
        "t_s": [float(replay["t"][i]) for i in selected],
        "ambulance_speed_kmh": [speed[i] for i in selected],
        "ordinary_stopped_network": [int(counts[i]) for i in selected],
        "routing_only_ordinary_stopped_network": [int(baseline_counts[i]) for i in selected],
    }
    files = ["P3.npz", "P3.json", "P0.npz", "P0.json"]
    result = {
        "source_case": "B1000", "focus_ambulance": focus_ambulance,
        "definitions": DEFINITIONS, "recorded": recorded,
        "provenance": {
            "raw_files_sha256": {name: sha256(directory / name) for name in files},
            "network_sha256": metadata["net_sha256"],
            "schedule_sha256": metadata["schedule_sha256"],
            "seed": metadata["seed"],
            "focus_mission": mission,
            "derivation": (
                "Read-only speed extraction and exact all-network stopped-vehicle "
                "counting from the supplied recorded arrays."),
            "selection_start_s": float(mission["depart"]),
            "selection_end_s": float(replay["t"][-1]),
            "annotation_lineage": (
                "Graph event labels are from the separately included audited story "
                "and controller log as their evidence source."),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-dir", type=Path, default=ROOT / "data" / "replays")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "progression_data.json")
    parser.add_argument("--check-against", type=Path,
                        help="Optional reference JSON for exact graph-series comparison")
    args = parser.parse_args()
    result = build(args.replay_dir, args.output)
    if args.check_against:
        compare_curves(result, args.check_against)
    print(json.dumps({"output": str(args.output), "samples": len(result["recorded"]["t_s"]),
                      "reference_curves_match": bool(args.check_against)}, indent=2))


if __name__ == "__main__":
    main()
