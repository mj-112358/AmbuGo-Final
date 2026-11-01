AMBUGO — BOTH 20-SECOND ANIMATIONS + REPRODUCIBILITY PACKAGE
=========================================================

START HERE

The two original videos are in reference/:
  01_Google_Maps_Journey.mp4 — the Google Maps ambulance journey
  02_Progression.mp4 — the synchronized animated graphs
Both are 1920 x 1080, 30 fps, 600 frames, 20 seconds, silent H.264 MP4s.
Open reference/index.html in a browser, or open either MP4 directly.
Nothing needs installing just to watch or forward these files.

This folder is self-contained for re-rendering. It includes the Python code,
frozen traffic replays, six fixed Google Maps captures, route geometry, control
logs, timing, original videos, source notes and checksums. Rendering uses no
Google API key, no live map requests and no observed government traffic feed.
An optional simulation/ folder also contains the actual controller and SUMO
rerun workflow. Simulation is not needed just to reproduce the animations.

QUICK REPRODUCTION

Use Python 3.12. Extract the ZIP first, preserving its folder structure.
Open a terminal in this folder.

macOS / Linux:
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python reproduce.py verify --videos reference
  .venv/bin/python reproduce.py all

Windows PowerShell:
  py -3.12 -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  .venv\Scripts\python.exe reproduce.py verify --videos reference
  .venv\Scripts\python.exe reproduce.py all

New videos and their player appear in generated/. The originals in reference/
are not overwritten. Initial package installation needs internet access;
rendering afterward reads the included local assets only. FFmpeg is located
through the imageio-ffmpeg package rather than a machine-specific executable.

OTHER COMMANDS

Use the same environment's Python in place of "python" below:
  python reproduce.py map        # Rebuild the map MP4 only
  python reproduce.py graph      # Rebuild the graph MP4 only
  python reproduce.py preview    # Save diagnostic still frames, no MP4 render
  python reproduce.py data       # Rebuild graph curves from the raw replays
  python reproduce.py verify --videos generated
  python reproduce.py all --output "my render folder"
  python reproduce.py serve --port 8768

The server is optional and listens on this computer only. Open
http://127.0.0.1:8768/reference/ for the supplied player, or /generated/ for
new videos rendered to the default folder. Press Ctrl+C to stop it. Choose
another port if 8768 is already in use. The player begins paused, preserves
playback time when switching Map / Animated graph, and stops after 20 seconds.

To render the graph directly from rebuilt data:
  python src/graph_animation.py --data generated/progression_data_rebuilt.json

To regenerate the traffic simulation and its control log, read
simulation/README.txt and install its additional requirements. Its generated
outputs are separate from the frozen data used by the films. Do not silently
replace just one member of the paired comparison with a new simulation run.

WHAT EACH FILE DOES

  reproduce.py                   Main command-line entry point
  requirements.txt               Pinned rendering dependencies
  MANIFEST.json                  SHA-256 checksums for every shipped file
  src/map_animation.py           Camera, routes, cars, signals, map compositing
  src/map_support.py             Drawing primitives, colors, fonts, initialization
  src/replay.py                  Recorded trajectory reader and map projection
  src/graph_animation.py         Growing curves, event markers and video encoder
  src/build_graph_data.py        Recompute exact plotted data from P3/P0 arrays
  src/validate_story.py          Check event claims against raw replay/control logs
  assets/maps/                   Six attributed fixed Google Maps screenshots
  assets/maps/capture_manifest.json  Their coordinates, zooms and checksums
  data/replays/P3.npz, P3.json    B1000 AmbuGo replay and its metadata
  data/replays/P0.npz, P0.json    Matched routing-only / no-priority baseline
  data/network_geo.json          Georeferenced edges and signal approaches
  data/connectors.json           Real simulator internal junction connectors
  data/decisions.json            Candidate routes, reroutes and escalation record
  data/control_explanations.json Detailed actual controller decision log
  data/story.json                Story events and their source interpretation
  data/time_mapping.json         Shared video-time to simulation-time conversion
  data/progression_data.json     Original graph data, including ancillary fields
  simulation/                   Optional upstream controller/simulator reproduction
  reference/                    The two exact delivered MP4s and viewing page
  evidence/                     Recorded tests, provenance and prior audits

The raw replay metadata and historical evidence retain source-run paths as
provenance records. Those paths are not required or executed. Active renderer
inputs resolve relative to this extracted folder. The map no longer imports
any earlier video project or relies on a private vendor directory.

REPRODUCTION LEVELS AND PORTABILITY

1. Exact delivered artifacts: reference/ contains the original MP4 files.
   Verify their checksums with reproduce.py verify.
2. Replay-to-video reproduction: both renderers consume the frozen numeric
   arrays and map captures. Camera, route, signal and graph behavior are the
   same. Pixel/MP4 byte identity across computers is not promised: font files,
   image libraries, encoder version and platform can change rasterization or
   compression without changing the recorded data or animation timing.
3. Simulation reproduction: the optional SUMO workflow reconstructs the paired
   traffic runs. Its README states versions and verification results. It does
   not establish agreement with measured real-world traffic.

The original map used installed Arial / Arial Bold. The portable map renderer
uses Arial if available, otherwise Matplotlib's DejaVu Sans. No proprietary
font files are redistributed. For exact local font selection, set
AMBUGO_FONT_REGULAR and AMBUGO_FONT_BOLD to your own licensed font files.
The graph uses Matplotlib's DejaVu Sans. Set AMBUGO_FFMPEG to a compatible local
FFmpeg executable if you want to override imageio-ffmpeg's bundled encoder.
Both originals used FFmpeg 7.1 with libx264, preset fast, yuv420p and faststart.
The map uses CRF 18 and 3 threads; the graph uses CRF 17 and 2 threads.
Each script preserves its respective original encoding settings.

Original map environment: Python 3.12, NumPy 2.3.5, Pillow 12.3.0, Arial.
Original graph environment: Python 3.12, NumPy 2.5.4, Pillow 13.0.0,
Matplotlib 3.11.2, imageio-ffmpeg 0.6.0. requirements.txt gives one tested
combined rendering environment. Both complete MP4s were regenerated byte for
byte in the tested local environment. This is a verified local result, not a
promise of identical encoded bytes on every platform. Validation reports are
in qa/, evidence/ and simulation/checks/.

TIME, GEOMETRY AND DATA DEFINITIONS

Both films use piecewise-linear time interpolation through these knots:
  Video seconds:      0      3     5.5    9.5    14     16.5     20
  Simulation seconds: 761.5  778   792    804    1048   1083.5   1125
The varying playback speed makes the mechanism readable in 20 seconds; neither
film shows 20 seconds of real-time traffic. Dispatch is simulation second 760.

The camera and every overlay share Web Mercator coordinates (EPSG:3857).
The camera uses smooth zoom transitions and recorded-position tracking.
Trajectory positions interpolate between recorded 0.5-second observations.
Vehicle presence, speed, route, phase and request values retain their original
sample semantics; the renderer does not invent vehicle stops or green times.
Internal connector geometry makes route lines continuous across junctions.
Source Google captures are reprojected and blended as whole frames. Their
native logo and full copyright remain in the adjoining fixed attribution strip.

The focused ambulance is a002, the third mission in the shared scenario.
Key events, in simulation time / video time:
  Priority withheld:       785.0 / 4.25 seconds
  Request admitted:        792.0 / 5.50 seconds
  Physical approach green: 796.5 / 7.00 seconds
  Stronger priority mode:  851.0 / approximately 10.37 seconds
  Hospital approach reroute:1055.0 / approximately 14.49 seconds
  Arrival at road approach:1083.5 / 16.50 seconds
  Final local ordinary green:1112.5 / approximately 18.95 seconds
Request admission and physical green are deliberately distinct.

NPZ arrays use a ragged per-frame vehicle representation: offsets[i:i+2]
indexes vehicle/speed/longitude/latitude/angle records for sample i. Vehicle IDs,
edge IDs, route IDs and junction IDs are decoded using the corresponding JSON
metadata. The map reads recorded signal modes and served approaches directly.

Ambulance speed is recorded simulator speed converted from m/s to km/h.
Ordinary stopped vehicles means all physically present non-ambulance vehicles
whose recorded speed is below 0.1 m/s, including internal junction connectors.
It excludes vehicles not yet inserted into the simulation. The baseline is the
matched no-priority routing run with the same network and demand schedule.
The graph data builder exactly reproduces all 2081 samples of the four plotted
arrays; additional fields in the original progression JSON are not graph inputs.

SCENARIO AND CONTROL INTERPRETATION

The replay uses mapped Mohali roads with generated traffic and assumed signal
settings. B1000 is a budget-sensitivity scenario. Candidate selection uses
a local queue/service-loss burden proxy; network aftereffects are evaluated
separately from the matched traffic records. Four route candidates share much
of the corridor and differ near the hospital. ETA labels compare those candidates.
The ambulance switches to stronger-priority mode when its progress threshold
is exceeded, and subsequent requests follow that mode. The destination is the
modeled hospital road approach. The graph shows combined network effects of all
three missions. The closing sequence shows local ordinary signal service after
arrival; network recovery is evaluated from the full episode records.

ATTRIBUTION

See THIRD_PARTY_NOTICES.txt. Google Maps imagery and OpenStreetMap-derived
network geometry have separate rights and attribution requirements. Keep the
existing map attribution visible when editing or exporting these videos.
