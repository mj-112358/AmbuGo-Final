# Visualizations and simulator transfer

| Folder | Contents |
| --- | --- |
| `map_replay/` | Source for the 20-second map and graph animations, frozen replay data, and the optional SUMO reproduction workflow. |
| `simultaneous/` | Source for combining recorded graphs with a locally supplied planning film or synchronized map replay. |
| `vissim_transfer/` | OpenDRIVE geometry, source network and scenario data, a boundary-reference repair script, and native Vissim integration instructions. |

The repository includes source, numeric replays and recorded results. Videos, map-background images, preview images and complete media archives are not published. Graph rendering, graph-data regeneration and the SUMO workflow run from the included inputs without map images. The map and simultaneous-film renderers require additional local assets.

## Regenerate graph data and render locally

Run these macOS/Linux commands from the repository root with Python 3.12. Generated files are written to a sibling directory outside the Git checkout.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r visualization/map_replay/requirements.txt

# Rebuild the plotted series from the included P0/P3 trajectory arrays
# and compare them with the included reference series.
.venv/bin/python visualization/map_replay/reproduce.py data \
  --output ../AmbuGo-local-renders

# Render the graph from those rebuilt series.
.venv/bin/python visualization/map_replay/src/graph_animation.py \
  --data ../AmbuGo-local-renders/progression_data_rebuilt.json \
  --output-dir ../AmbuGo-local-renders
```

Add `--preview-only` to the graph command to create still previews instead of a video. These outputs remain local. On Windows, use `py -3.12 -m venv .venv` and `.venv\Scripts\python.exe` in place of `.venv/bin/python`.

The renderers use NumPy, Pillow, Matplotlib and imageio-ffmpeg. Initial installation needs internet access; rendering uses local data. Font and encoder differences can change output pixels or bytes across machines.

To rerun the recorded traffic episodes, install `visualization/map_replay/simulation/requirements.txt` and follow that folder's `README.txt`. It uses the pinned SUMO/libsumo 1.28.0 environment and checks the rerun against the frozen trajectories. This is separate from replaying the supplied data.

## Optional rendering with locally held assets

If you already have a complete local `AmbuGo_20s_Reproducible` package, keep it outside the checkout with its folder structure intact. From that package's root, install its `requirements.txt` in a Python 3.12 environment, then run:

```sh
python reproduce.py verify --videos reference
python reproduce.py all
```

Here `python` means the activated environment's interpreter. These commands require that package's map captures, reference media and manifest; they are not commands for the incomplete-media Git directory.

For a locally held complete `AmbuGo_Simultaneous` package, install its `requirements.txt` and run `python reproduce.py --version synchronized` or `python reproduce.py --version teammate` from its root. The synchronized edit requires `inputs/01_Google_Maps_Journey.mp4`; the planning-film edit requires `inputs/AmbuGo_v9_Plan.mp4`. Neither input is published here. The compositor overwrites its composite outputs while preserving its input films. The included `README.txt` files describe those original complete local packages; their media references do not indicate public availability.

## Interpretation and third-party content

The 20-second synchronized map and graphs represent one recorded synthetic-traffic episode. The longer planning film and its accompanying graphs represent different examples with independent clocks and different priority-budget settings. Each set of graphs describes its own recorded simulation episode. The compositor source is included; rendering the planning-film version requires the locally held film and its animation project.

The Vissim transfer package supplies OpenDRIVE geometry, scenario inputs and an integration workflow. Native import, controller integration and paired Vissim evaluations are the next steps described in `README.txt` and `PTV_REQUIREMENTS_AND_INTEGRATION.txt`.

Retain the Google and provider attribution in map images and films. Google imagery is not covered by a project-code license; see the packages' `THIRD_PARTY_NOTICES.txt` and [Google's geographic-content guidance](https://about.google/brand-resource-center/products-and-services/geo-guidelines/). The modeled road data derive from [OpenStreetMap contributors under ODbL](https://www.openstreetmap.org/copyright); the geometry notes also identify the imagery consulted for the local correction. Third-party dependencies are installed separately under their own licenses.
