#!/usr/bin/env python3
"""Render the final 20-second animated graph from recorded replay data.

The renderer uses the supplied trajectories. B1000/a002 supplies the speed
curve; ordinary stopped-vehicle counts include all three ambulance missions.
The horizontal axis uses the map replay's piecewise video clock.

Runtime: Python 3.12, NumPy, Matplotlib, Pillow and imageio-ffmpeg. Rendering
reads local inputs and uses a headless plotting backend."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
_cache = Path(tempfile.gettempdir()) / "ambugo-matplotlib"
_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_cache))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import PIL
from PIL import Image

FPS, DURATION, W, H = 30, 20, 1920, 1080
V = np.array([0, 3, 5.5, 9.5, 14, 16.5, 20], dtype=float)
T = np.array([761.5, 778, 792, 804, 1048, 1083.5, 1125], dtype=float)
BLUE, GRAY, INK = "#316d97", "#9aa0a4", "#313639"
RED, GREEN = "#b85b53", "#4d8866"


def validate_graph_data(data):
    """Fail clearly if inputs cannot represent this fixed, audited episode."""
    if data.get("focus_ambulance") != "a002":
        raise ValueError("This fixed storyboard requires focus ambulance a002.")
    if data.get("source_case") != "B1000":
        raise ValueError("This fixed storyboard requires the B1000 sensitivity run.")
    recorded = data["recorded"]
    keys = ("t_s", "ambulance_speed_kmh", "ordinary_stopped_network",
            "routing_only_ordinary_stopped_network")
    if len({len(recorded[key]) for key in keys}) != 1:
        raise ValueError("Graph arrays must have matching sample counts.")
    times = np.asarray(recorded["t_s"], dtype=float)
    if not len(times) or not np.all(np.diff(times) > 0):
        raise ValueError("Recorded times must be strictly increasing.")
    if times[0] > T[0] or times[-1] < T[-1]:
        raise ValueError("Data must cover simulation times 761.5 through 1125 s.")
    for key in keys[2:]:
        values = np.asarray(recorded[key], dtype=float)
        if not np.all(np.isfinite(values)) or np.any(values < 0):
            raise ValueError(f"Invalid recorded counts: {key}")
        if np.max(values[(times >= T[0]) & (times <= T[-1])]) > 40:
            raise ValueError("This episode's fixed count axis would clip the data.")


def resolve_ffmpeg():
    """Use an explicit override or imageio-ffmpeg's installed binary."""
    override = os.environ.get("AMBUGO_FFMPEG")
    if override:
        candidate = shutil.which(os.path.expanduser(override))
        if candidate is None:
            raise FileNotFoundError("AMBUGO_FFMPEG must name an executable FFmpeg binary.")
        return candidate
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


class Graph:

    def __init__(self, data_path=None):
        self.data_path = Path(data_path) if data_path is not None else ROOT / 'data' / 'progression_data.json'
        self.data = json.loads(self.data_path.read_text(encoding='utf-8'))
        validate_graph_data(self.data)
        r = self.data['recorded']
        self.ts = np.array(r['t_s'])
        keep = (self.ts >= T[0]) & (self.ts <= T[-1])
        self.ts = self.ts[keep]
        self.x = np.interp(self.ts, T, V)
        self.speed = np.array(r['ambulance_speed_kmh'], dtype=float)[keep]
        self.stops = np.array(r['ordinary_stopped_network'])[keep]
        self.baseline = np.array(r['routing_only_ordinary_stopped_network'])[keep]
        plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 17, 'text.color': INK, 'axes.labelcolor': INK, 'xtick.color': INK, 'ytick.color': INK, 'axes.edgecolor': '#9fa6aa', 'axes.linewidth': 0.8})
        self.fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor='white')
        self.a = self.fig.add_axes([0.105, 0.6, 0.85, 0.22])
        self.b = self.fig.add_axes([0.105, 0.19, 0.85, 0.22])
        self.fig.text(0.105, 0.945, 'The ambulance and surrounding traffic', fontsize=25)
        self.fig.text(0.105, 0.905, 'Same recorded episode and timing as the map', fontsize=16, color='#667075')
        self.clock = self.fig.text(0.955, 0.905, '', fontsize=16, color='#667075', ha='right')
        self.fig.text(0.105, 0.85, 'Ambulance speed', fontsize=22)
        self.readout = self.fig.text(0.955, 0.85, '', fontsize=25, color=BLUE, ha='right')
        self.fig.text(0.105, 0.455, 'Ordinary vehicles stopped across the network', fontsize=22, zorder=12, bbox={'facecolor': 'white', 'edgecolor': 'none', 'pad': 2})
        for ax in [self.a, self.b]:
            ax.set_xlim(0, DURATION)
            ax.grid(axis='y', color='#e6e8e9', linewidth=0.8)
            ax.set_axisbelow(True)
            ax.spines[['top', 'right']].set_visible(False)
            ax.tick_params(labelsize=15, pad=8)
        self.a.set_ylim(0, 60)
        self.a.set_yticks([0, 25, 50])
        self.a.set_ylabel('km/h', fontsize=18, labelpad=15)
        self.a.set_xticks([])
        self.a.spines['bottom'].set_visible(False)
        self.b.set_ylim(0, 40)
        self.b.set_yticks([0, 10, 20, 30, 40])
        self.b.set_ylabel('Vehicles', fontsize=18, labelpad=15)
        self.b.set_xticks(np.arange(0, DURATION + 1, 4))
        self.b.set_xlabel('Video time (seconds)', fontsize=18, labelpad=13)
        self.lspeed, = self.a.plot([], [], color=BLUE, linewidth=3.3)
        self.pspeed, = self.a.plot([], [], 'o', color=BLUE, markersize=8)
        self.lbase, = self.b.step([], [], where='post', color=GRAY, linewidth=2.4, label='No priority')
        self.lstops, = self.b.step([], [], where='post', color=BLUE, linewidth=3, label='AmbuGo')
        self.pstops, = self.b.plot([], [], 'o', color=BLUE, markersize=8)
        self.b.legend(handles=[self.lstops, self.lbase], loc='upper right', frameon=False, ncol=2, fontsize=16)
        self.events = []
        for tm, label, col in [(785, 'Request withheld', RED), (796.5, 'Signal green', GREEN), (1055, 'Route changed', BLUE), (1083.5, 'Arrival', GREEN)]:
            xx = float(np.interp(tm, T, V))
            fx = 0.105 + 0.85 * xx / DURATION
            mark = Line2D([fx], [0.535], marker='o', markersize=7, color=col, transform=self.fig.transFigure, visible=False, zorder=12)
            self.fig.add_artist(mark)
            text = self.fig.text(fx, 0.493, label, ha='center', fontsize=17, color=INK, visible=False, zorder=12, bbox={'facecolor': 'white', 'edgecolor': 'none', 'pad': 1})
            self.events.append((xx, mark, text))
        self.cursor = Line2D([0.105, 0.105], [0.19, 0.82], color='#687176', linewidth=1.5, alpha=0.65, transform=self.fig.transFigure, zorder=9)
        self.fig.add_artist(self.cursor)
        self.now = self.fig.text(0.105, 0.826, 'Now', fontsize=13, color='#687176')
        self.fig.text(0.105, 0.072, 'The curves grow with the replay. Video time uses a changing playback speed.', fontsize=15, color='#667075')
        self.fig.text(0.105, 0.035, 'Generated traffic. Network counts include all three ambulance missions.', fontsize=15, color='#667075')

    def frame(self, ft):
        ft = float(np.clip(ft, 0, DURATION))
        tm = float(np.interp(ft, V, T))
        elapsed = tm - 760
        k = int(np.searchsorted(self.x, ft, side='right'))
        xx = self.x[:k]
        ss = self.speed[:k]
        self.clock.set_text(f'Time since dispatch {int(elapsed) // 60:02d}:{int(elapsed) % 60:02d}')
        self.lspeed.set_data(xx, ss)
        self.lbase.set_data(xx, self.baseline[:k])
        self.lstops.set_data(xx, self.stops[:k])
        if k:
            if np.isfinite(ss[-1]):
                self.pspeed.set_data([xx[-1]], [ss[-1]])
                self.readout.set_text(f'{ss[-1]:.0f} km/h')
            else:
                self.pspeed.set_data([], [])
                self.readout.set_text('Arrived')
            self.pstops.set_data([xx[-1]], [self.stops[k - 1]])
        for x, mark, text in self.events:
            mark.set_visible(ft >= x - 1e-09)
            text.set_visible(ft >= x - 1e-09)
        fx = 0.105 + 0.85 * ft / DURATION
        self.cursor.set_xdata([fx, fx])
        self.now.set_position((fx, 0.826))
        self.now.set_ha('right' if ft > DURATION - 1 else 'left')
        self.fig.canvas.draw()
        return Image.fromarray(np.asarray(self.fig.canvas.buffer_rgba())[:, :, :3].copy())

def render(output_dir=ROOT / "generated", preview=False, data_path=None):
    """Render the MP4 or diagnostic still previews for a setup check.
    
    Return a dictionary describing the generated files. Preview images support
    visual inspection; the primary animated output is 02_Progression.mp4."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    graph = Graph(data_path=data_path)
    mapping = {"video_time_s": V.tolist(), "simulation_time_s": T.tolist(),
               "interpolation": "piecewise_linear", "duration_s": DURATION,
               "fps": FPS}
    started = time.perf_counter()
    try:
        if preview:
            files = []
            for second in (1, 7, 15, 19):
                path = output_dir / f"02_Progression_preview_{second:02d}.png"
                graph.frame(second).save(path)
                files.append(path.name)
            return {"preview_only": True, "files": files, "time_mapping": mapping}

        video = output_dir / "02_Progression.mp4"
        poster = output_dir / "02_Progression_Poster.jpg"
        log_path = output_dir / "02_Progression_ffmpeg.log"
        command = [resolve_ffmpeg(), "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                   "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an",
                   "-c:v", "libx264", "-threads", "2", "-preset", "fast",
                   "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                   str(video)]
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log)
            try:
                for frame_number in range(FPS * DURATION):
                    frame = graph.frame(frame_number / FPS)
                    process.stdin.write(frame.tobytes())
                    if frame_number == 15 * FPS:
                        frame.save(poster, quality=95)
                    if frame_number % (3 * FPS) == 0:
                        print(f"Graph: {frame_number / FPS:g}/{DURATION} seconds", flush=True)
            except BaseException:
                if process.poll() is None:
                    process.terminate()
                process.wait()
                raise
            finally:
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()
            if process.wait() != 0:
                raise RuntimeError(f"FFmpeg failed; see {log_path}")

        import imageio_ffmpeg
        definitions = graph.data["definitions"]
        manifest = {
            "video": video.name, "poster": poster.name, "width": W, "height": H,
            "fps": FPS, "duration_s": DURATION, "frames": FPS * DURATION,
            "data_sha256": hashlib.sha256(graph.data_path.read_bytes()).hexdigest(),
            "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "time_mapping": mapping,
            "metrics": {"speed": definitions["ambulance_speed_kmh"],
                        "ordinary_stopped": definitions["ordinary_stopped_network"],
                        "comparison": definitions["comparison_scope"]},
            "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                        "Pillow": PIL.__version__, "matplotlib": matplotlib.__version__,
                        "imageio-ffmpeg": imageio_ffmpeg.__version__},
            "render_seconds": time.perf_counter() - started,
        }
        (output_dir / "02_Progression_manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest
    finally:
        plt.close(graph.fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "generated")
    parser.add_argument("--data", type=Path, default=None,
                        help="Optional alternate progression_data.json path")
    parser.add_argument("--preview-only", action="store_true",
                        help="Render four diagnostic stills instead of the MP4")
    args = parser.parse_args()
    result = render(args.output_dir, preview=args.preview_only, data_path=args.data)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
