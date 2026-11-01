AMBUGO — SIMULTANEOUS ANIMATION AND GRAPHS

01_Teammate_Film_with_Graphs.mp4
The supplied 2:42.5 planning film plays on the left while the earlier
recorded simulation graphs evolve on the right. Both remain visible.
These are explicitly separate examples. The planning film shows a 10,000
priority limit; the graph data come from the earlier B1000 experiment.
The right-hand clock is independent, progressing linearly from simulation
time 761.5 to 1125 seconds across the film. The composition presents the planning film and recorded graph episode
with their respective clocks and scenario settings.


02_Synchronized_Map_and_Graphs.mp4
The earlier Google-map replay and the graphs share the same recorded
episode and exact piecewise playback clock, for 20 seconds. Use this version
to see the measured ambulance motion and traffic graphs at the same moment.
The teammate's new film is not used in this genuinely synchronized version.

DISPLAY
Both films use a plain white layout, 2880x1200 at 30 fps, with the original
1920x1080 map on the left and a 960px-wide graph panel. No imagery is cropped
and map attribution stays visible. The long film's graph updates at 12 fps,
then is held to match the 30 fps movie; the short graph updates at 30 fps.
Both graph x-axes show actual simulation seconds since dispatch, not elapsed
movie time. The short film changes playback speed with its camera sequence.

SCIENTIFIC SCOPE
This is synthetic traffic on a mapped Mohali network. The speed curve tracks
ambulance a002. Counts compare ordinary stopped vehicles in AmbuGo and the
matched routing-only run, including the effects of all three missions.
Stopped means below 0.1 m/s; counts exclude ambulances and traffic awaiting
insertion. The graph reports instantaneous stopped-vehicle counts. The subtitle shows
escalation to stronger priority. Arrival means the modeled hospital road
approach. These trajectories were generated in SUMO.

REPRODUCE
With Python 3.12 or a compatible release:
  python -m pip install -r requirements.txt
  python reproduce.py --preview
  python reproduce.py

Optional: --version teammate or --version synchronized.
The package includes both original video inputs and the exact graph data.
The edit and plots can be rebuilt offline after dependency installation.
AMBUGO_FFMPEG can override the bundled imageio-ffmpeg executable.
Fonts come from Matplotlib. This reproduces the edit from existing video
assets; recreating the original teammate animation requires its own source.
The previous complete map/simulation source package remains available as
AmbuGo_20s_Reproducible.zip.

SHORT VERSION SHARED CLOCK
Movie time:       0, 3, 5.5, 9.5, 14, 16.5, 20 seconds
Simulation time: 761.5, 778, 792, 804, 1048, 1083.5, 1125 seconds
Piecewise linear interpolation is shared with the map source.
