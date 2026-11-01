# AmbuGo

AmbuGo combines ambulance routing with selective traffic signal priority to shorten emergency journeys while limiting congestion on surrounding roads.

The controller evaluates routes and signal changes together, ranks them by predicted travel time and traffic burden, and updates priority as the ambulance moves through the network.

[Paper](paper/AmbuGo_Research_Paper.pdf) · [Reproduction guide](docs/reproduction.md) · [Visualizations](visualization/README.md)

## Results

Across 1,728 synthetic SUMO policy runs, selective joint control reduced balanced mean ambulance duration from 401.57 s with routing alone to 222.29 s. Compared with aggressive joint control, it added 11.10 s of mean ambulance duration while reducing positive spatial occupancy exposure by 3.84 vehicle-hours.

The primary evaluation uses 48 paired seeds across nine load/mission conditions and four policies. The study also includes 264 secondary microscopic runs and 14,400 corrected mesoscopic runs. See the [paper directory](paper/README.md) for the current PDF and supporting files.

## Code

- `work/v9/` — controllers, simulation runners, statistical analysis and results.
- `outputs/AmbuGo_v7_Synthetic_Data/` — network and traffic inputs.
- `paper/` — current research paper, results-figure generator, reliability table and archived authoring files.
- `visualization/` — map replay and animated graphs.
- `scripts/check.py` — numerical and reproducibility checks.

## Setup

Python 3.12, from the repository root:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --target work/v9/vendor -r requirements.txt
export PYTHONPATH="$PWD/work/v9/vendor${PYTHONPATH:+:$PYTHONPATH}"
export MPLCONFIGDIR="$PWD/work/v9/mpl_cache"
```

## Run

```sh
# Run checks.
python scripts/check.py

# Recompute results from the included records.
python work/v9/analyze_corrected.py
python work/v9/analyze_sumo.py

# Run the primary SUMO experiment.
python work/v9/run_sumo_batch.py main --workers 4
```

Additional experiments and paper-build commands are in the [reproduction guide](docs/reproduction.md).
