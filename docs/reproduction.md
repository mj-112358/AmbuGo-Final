# Reproducing the study

The Git repository contains source code, input fixtures, experiment protocols,
scalar run records, statistical summaries, figures, and the final paper. These
files support analysis regeneration without rerunning the traffic simulations.

The current paper is [`paper/AmbuGo_Research_Paper.pdf`](../paper/AmbuGo_Research_Paper.pdf).
Earlier editable manuscript files and their builder are retained in
`paper/archive/audited/`. Per-run population traces and ordinary-vehicle event
files can be regenerated with the simulation commands below.

There are 1,728 primary microscopic policy runs, 264 microscopic secondary runs,
and 14,400 mechanically corrected mesoscopic policy runs. Development records
are separate. Each run evaluates one policy in a specified scenario. Independent-seed
and mission counts are reported separately in the paper. The inputs are synthetic; the package contains no measured-city
calibration dataset.

## Install the runtime

Run commands from the repository root. Preserve the relative `work/` and
`outputs/` layout. Python 3.12 and platform-compatible SUMO wheels are
recommended. The commands below use a POSIX shell.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --target work/v9/vendor -r requirements.txt
export PYTHONPATH="$PWD/work/v9/vendor${PYTHONPATH:+:$PYTHONPATH}"
export MPLCONFIGDIR="$PWD/work/v9/mpl_cache"
```

The target installation is required: the frozen source expects `sumo` and
`netconvert` under `work/v9/vendor/sumo/bin/`. Installing only into the virtual
environment's ordinary site-packages does not populate these paths. The
repository excludes runtime binaries. Availability of compatible
wheels must be checked for the intended platform.

## Regenerate analyses from the records in Git

After installing the runtime:

```sh
python work/v9/analysis.py --self-check
python work/v9/meso_checks.py --out meso_verification_rerun.json
python work/v9/audit_v8_statistics.py
python work/v9/analyze_corrected.py
python work/v9/analyze_sumo.py
python work/v9/make_base_figures.py
```

These commands regenerate analysis outputs from retained scalar records. The
mesoscopic checks execute small synthetic verification cases. The microscopic
analysis resamples whole seed blocks, preserving dependence among missions
and conditions within each seed.

Regeneration writes output files. Use a separate checkout to
preserve the supplied outputs unchanged. Runtime measurements and numerical
details can vary across machines and dependency versions.

## Current paper and results-figure regeneration

The current 14-page paper is [AmbuGo_Research_Paper.pdf](../paper/AmbuGo_Research_Paper.pdf).
It is supplied as a PDF. Its SHA-256 and supporting-file descriptions are in the
[paper directory guide](../paper/README.md).

To generate a results-figure preview from the retained numerical summaries,
run from the repository root:

```sh
python paper/plot_results.py --output /tmp/ambugo-primary-effects.png
```

This command plots the nine stored JSEL-minus-JFAST paired means and marginal
95% seed-bootstrap intervals from `work/v9/sumo_analysis.json`. Duration is
in seconds; positive spatial exposure is in vehicle-hours. The dashed line
marks the evaluated 20-second mean-duration allowance. Spatial exposure for
each policy is measured relative to the same S0 baseline before forming the
JSEL-minus-JFAST contrast.

### Rebuild the archived editable draft

The earlier audited draft's DOCX, manuscript, references, figure assets and
builder are in `paper/archive/audited/`. To rebuild that draft:

```sh
python -m pip install --target work/v9/vendor -r requirements-document.txt
python paper/archive/audited/build.py
```

The builder reads its archived manuscript, references and figures together
with retained numerical summaries. It writes the earlier DOCX and a
regenerated `Episode_Reliability.csv` into the archive directory. The current
paper's revised wording and layout are maintained in the supplied PDF; this
archived builder reproduces the earlier draft.

`work/v9/build_paper.py` builds the historical v9 draft. The checked-in
`paper/Episode_Reliability.csv` remains the episode-level companion table for
the current paper's reported experiments.

## Rerun the microscopic evaluations

Use a separate checkout for expensive reruns. Keep the included
`selected_policy.json`; do not retune before reproducing the evaluation.

```sh
python work/v9/run_sumo_batch.py main --workers 4
python work/v9/run_sumo_batch.py sensitivity --workers 4
python work/v9/run_sumo_batch.py ablation --workers 4
python work/v9/run_sumo_robustness.py adaptive_base --workers 4
python work/v9/run_sumo_robustness.py exact_counts --workers 4
python work/v9/analyze_sumo.py
```

The main batch contains 1,728 runs. The smaller-step, progress-escalation
ablation, adaptive-baseline, and noiseless-count batches contain 72, 48, 72,
and 72 runs respectively. The smaller physical step also changes SUMO's
default vehicle decision interval. The adaptive baseline selects the largest
observed approach vehicle count, including moving vehicles. The noiseless-count
condition retains the specified availability mechanism.

The four required fixture CSVs are in `outputs/AmbuGo_v7_Synthetic_Data/`.
The exported v8 CSVs have different schemas and cannot replace them. Reruns
create local network/scenario files and per-run traces and event records.

## Rerun the mesoscopic checks and evaluation

```sh
python work/v9/teammate_v8/ambugo_v8/tests/run_tests.py
python work/v9/v8_regression_checks.py
python work/v9/reproduce_v8.py
python work/v9/v8_corrected/tests/mechanical_checks.py
python work/v9/v8_corrected/scripts/run_experiments.py E --reps 200 --procs 4
python work/v9/analyze_corrected.py
```

The adversarial regression program is expected to detect the documented
original storage/capacity exceptions and incomplete wait measurement.
`reproduce_v8.py` reruns 216 original-model cases. The corrected evaluation
contains 14,400 policy runs and retains the original parameter choices.
Run original and corrected models in separate processes because both use
the Python package name `ambugo`. Their policy keys also differ in meaning
from identically numbered microscopic policies.

## Optional: verify a separately supplied local archive

If a full research archive is supplied separately, verify it before running
analyses that overwrite its outputs. The verifier uses only the Python standard
library and checks every manifested file's SHA-256 and byte count. For the
historical `AmbuGo_First_Draft_Reproducibility_v9.zip` package, with the ZIP in
the current directory:

```sh
python3 verify_zip.py AmbuGo_First_Draft_Reproducibility_v9.zip --extract archive-extraction
cd archive-extraction/AmbuGo_First_Draft_Reproducibility_v9
python3 verify_zip.py --directory .
```

The extraction destination must be new or empty. The directory-verification
command applies to the extracted archive, which contains `MANIFEST.json`,
not to the Git checkout. The historical archive retains per-run traces,
ordinary-vehicle event files, archived scenario inputs, and earlier paper
sources. Use this repository's `paper/` folder for the current manuscript.

Raw records retain original absolute trace paths. The archive's
`PORTABLE_PATH_INDEX.json` maps them to archive-relative files. Its active
`work/v9/scenarios/` cache is deliberately absent because cached scenario JSON
contains absolute route paths. Let the generator create a local cache; do not
copy archived scenario JSON into the active cache unchanged.

Install dependencies from the extracted archive root using the runtime commands
above. An optional short numerical smoke check is then available:

```sh
python verify_zip.py --directory . --smoke
```

This 180-second software and path check verifies startup and local inputs.
Journey completion is evaluated in the full experiment runs.

For the optional development replay and the historical archive-build procedure,
see [`work/v9/README_reproducibility.txt`](../work/v9/README_reproducibility.txt).
Building the complete archive requires its per-run trace/event files and
scenario inputs, or regenerated equivalents; the scalar records in Git alone
are insufficient.
