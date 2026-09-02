"""Record the animated previews the README and the wiki embed.

Each scene runs a real Ray workload against a real local dashboard, screenshots
the page while it streams, and writes a GIF. Nothing is staged or mocked, so
the previews cannot drift from what the library actually renders.

Usage:
    python scripts/record_docs_media.py [scene ...]

Chromium must be present: `python -m playwright install chromium`.
"""

import math
import os
import random
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import ray
from PIL import Image
from playwright.sync_api import Page, sync_playwright

from raydar import RayTaskTracker

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "docs" / "img"
WIKI_IMG = ROOT / "docs" / "wiki" / "images"

VIEWPORT = {"width": 1280, "height": 720}
OUTPUT_WIDTH = 900
FPS = 8
COLORS = 128

TRIALS = ("lr=3e-4", "lr=1e-4", "lr=3e-5", "lr=1e-5")


def tab(*names: str) -> dict:
    return {"type": "tab-layout", "tabs": list(names)}


def split(orientation: str, sizes: list[float], *children: dict) -> dict:
    return {"type": "split-layout", "orientation": orientation, "sizes": sizes, "children": list(children)}


@ray.remote
def train_step(trial: str, epoch: int, floor: float) -> dict:
    time.sleep(random.uniform(0.05, 0.3))
    loss = floor + 2.4 * math.exp(-epoch / 9) + random.uniform(0, 0.05)
    return {
        "trial": trial,
        "epoch": epoch,
        "loss": round(loss, 4),
        "accuracy": round(min(0.99, 1 - loss / 3) - random.uniform(0, 0.01), 4),
        "timestamp": datetime.now(tz=UTC),
    }


@ray.remote
def flaky_step() -> bool:
    time.sleep(random.uniform(0.2, 1.2))
    if random.randint(1, 100) > 90:
        raise RuntimeError("This task should sometimes fail!")
    return True


@ray.remote
def load_shard(shard: int) -> int:
    time.sleep(random.uniform(0.1, 0.6))
    return shard


@ray.remote
def score_batch(batch: int) -> float:
    time.sleep(random.uniform(0.2, 0.9))
    if batch % 11 == 0:
        raise ValueError(f"batch {batch} has a null label")
    return random.random()


@ray.remote
def training_epoch(epoch: int) -> list[dict]:
    """Stand-in for the wiki's pytorch loop: emits the metrics a real one would log."""
    time.sleep(random.uniform(0.1, 0.4))
    node_id = ray.get_runtime_context().get_node_id()
    loss = 0.08 + 2.1 * math.exp(-epoch / 8) + random.uniform(0, 0.06)
    now = datetime.now(tz=UTC)
    return [
        {"node_id": node_id, "metric_name": "loss", "value": round(loss, 4), "timestamp": now},
        {"node_id": node_id, "metric_name": "val_loss", "value": round(loss * random.uniform(1.05, 1.3), 4), "timestamp": now},
    ]


@ray.remote
def emit_metric(index: int) -> dict:
    time.sleep(random.uniform(0.02, 0.1))
    return {
        "worker_id": f"worker_{index % 4}",
        "metric_value": index,
        "other_metric_value": round(index * random.uniform(1.5, 1.8), 3),
        "timestamp": datetime.now(tz=UTC),
    }


def palette_for(frames: list[Image.Image]) -> Image.Image:
    """One palette for the whole clip, sampled across it so late frames keep their colours."""
    step = max(1, len(frames) // 8)
    sample = frames[::step]
    width, height = frames[0].size
    strip = Image.new("RGB", (width, height * len(sample)))
    for index, frame in enumerate(sample):
        strip.paste(frame, (0, index * height))
    return strip.quantize(colors=COLORS, method=Image.Quantize.MEDIANCUT)


def write_gif(shots: list[bytes], outputs: tuple[Path, ...]) -> None:
    size = (OUTPUT_WIDTH, round(VIEWPORT["height"] * OUTPUT_WIDTH / VIEWPORT["width"]))
    frames = [Image.open(BytesIO(shot)).convert("RGB").resize(size, Image.LANCZOS) for shot in shots]
    palette = palette_for(frames)
    # Dithering triples the file size on flat UI chrome and blurs grid text.
    indexed = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    first, *rest = indexed
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        first.save(path, save_all=True, append_images=rest, duration=round(1000 / FPS), loop=0, optimize=True)
        print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1e6:.1f} MB, {len(indexed)} frames)")


def record(
    url: str,
    outputs: tuple[Path, ...],
    duration: float,
    cues: list[tuple[float, Callable[[Page], None]]] | None = None,
    follow: bool = False,
) -> None:
    """Screenshot `url` for `duration` seconds, firing each cue once its timestamp passes.

    `follow` keeps the grid scrolled to its last row, so an append-only table
    reads as streaming rather than as a frozen first page.
    """
    shots: list[bytes] = []
    pending = sorted(cues or [], key=lambda cue: cue[0])
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        page.goto(url)
        page.wait_for_selector("perspective-viewer-datagrid", timeout=60_000)
        # Synthetic wheels leak past the grid and scroll the document, taking the
        # header off screen. Nothing here needs the page itself to scroll.
        page.add_style_tag(content="html, body { overflow: hidden !important; }")
        page.wait_for_timeout(2_000)
        start = time.monotonic()
        while (elapsed := time.monotonic() - start) < duration:
            while pending and pending[0][0] <= elapsed:
                pending.pop(0)[1](page)
            if follow:
                # Aim at the rows, not at wherever a cue left the pointer.
                page.mouse.move(VIEWPORT["width"] / 2, VIEWPORT["height"] * 0.7)
                page.mouse.wheel(0, 2_000)
            shots.append(page.screenshot())
            time.sleep(max(0.0, 1 / FPS - (time.monotonic() - start - elapsed)))
        browser.close()
    write_gif(shots, outputs)


def in_background(target) -> threading.Thread:
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread


def click_tab(name: str) -> Callable[[Page], None]:
    """The default layout opens on the tracker's own table; scenes about another one switch to it."""
    return lambda page: page.locator("perspective-viewer-tab", has_text=name).first.click()


def push_layout(state, layout: dict) -> Callable[[Page], None]:
    """Assigning the model field is what a caller does from Python; transports pushes it to every tab."""
    return lambda _page: setattr(state, "layout", layout)


def wait_for_table(tracker: RayTaskTracker, name: str, timeout: float = 90) -> None:
    """A layout naming a table that does not exist yet is rejected whole, so wait it out."""
    tables = tracker.dashboard.dashboard.tables
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if name in tables.names():
            return
        time.sleep(0.25)
    raise TimeoutError(f"table {name!r} never appeared")


def scene_ml() -> None:
    """The README hero: a training sweep charting live, over tracked Ray tasks."""
    layout = {
        "layout": split(
            "vertical",
            [0.62, 0.38],
            split("horizontal", [0.5, 0.5], tab("loss"), tab("accuracy")),
            tab("metrics"),
        ),
        "panels": {
            "loss": {
                "table": "training_metrics",
                "plugin": "Y Line",
                "title": "Training loss",
                "group_by": ["epoch"],
                "split_by": ["trial"],
                "columns": ["loss"],
            },
            "accuracy": {
                "table": "training_metrics",
                "plugin": "Y Line",
                "title": "Validation accuracy",
                "group_by": ["epoch"],
                "split_by": ["trial"],
                "columns": ["accuracy"],
            },
            "metrics": {
                "table": "training_metrics",
                "plugin": "Datagrid",
                "title": "Metrics",
                "sort": [["timestamp", "desc"]],
            },
        },
    }
    tracker = RayTaskTracker(namespace="raydar-docs", dashboard="local", dashboard_options={"layout": layout})
    tracker.create_table(
        "training_metrics",
        {"trial": "string", "epoch": "integer", "loss": "float", "accuracy": "float", "timestamp": "datetime"},
    )

    def sweep() -> None:
        for epoch in range(1, 60):
            refs = [train_step.remote(trial, epoch, 0.05 + index * 0.06) for index, trial in enumerate(TRIALS)]
            tracker.update_table("training_metrics", ray.get(refs))
            tracker.process(refs)

    in_background(sweep)
    record(tracker.dashboard_url, (IMG / "ml_example.gif",), duration=16)
    tracker.exit()


def scene_dashboard() -> None:
    """Ray task metadata landing in the default one-tab-per-table layout."""
    tracker = RayTaskTracker(namespace="raydar-docs", dashboard="local")

    def submit() -> None:
        for _ in range(12):
            tracker.process([flaky_step.remote() for _ in range(20)])

    in_background(submit)
    record(
        tracker.dashboard_url,
        (IMG / "example_perspective_dashboard.gif", WIKI_IMG / "example_perspective_dashboard.gif"),
        duration=14,
        follow=True,
    )
    tracker.exit()


def scene_custom_table() -> None:
    """The README's custom table example: a schema declared in Python, filled from tasks."""
    tracker = RayTaskTracker(namespace="raydar-docs", dashboard="local")
    tracker.create_table(
        "demo_table",
        {"worker_id": "string", "metric_value": "integer", "other_metric_value": "float", "timestamp": "datetime"},
    )

    def fill() -> None:
        for index in range(400):
            tracker.update_table("demo_table", [ray.get(emit_metric.remote(index))])

    in_background(fill)
    record(tracker.dashboard_url, (IMG / "custom_user_table.gif",), duration=14, cues=[(0, click_tab("demo_table"))], follow=True)
    tracker.exit()


def scene_layouts() -> None:
    """Layouts are Python-side: push a new one and every connected tab follows."""
    tracker = RayTaskTracker(namespace="raydar-docs", dashboard="local")
    tracker.create_table(
        "demo_table",
        {"worker_id": "string", "metric_value": "integer", "other_metric_value": "float", "timestamp": "datetime"},
    )
    state = tracker.dashboard.dashboard.state

    def fill() -> None:
        for index in range(400):
            tracker.update_table("demo_table", [ray.get(emit_metric.remote(index))])
            if index % 8 == 0:
                tracker.process([flaky_step.remote()])

    grouped = {
        "layout": tab("by_worker"),
        "panels": {
            "by_worker": {
                "table": "demo_table",
                "plugin": "Datagrid",
                "title": "Grouped by worker",
                "group_by": ["worker_id"],
                "columns": ["metric_value", "other_metric_value"],
                "aggregates": {"metric_value": "sum", "other_metric_value": "avg"},
            }
        },
    }
    charted = {
        "layout": split("horizontal", [0.55, 0.45], tab("trend"), tab("by_worker")),
        "panels": {
            "trend": {
                "table": "demo_table",
                "plugin": "Y Line",
                "title": "Metric trend",
                "group_by": ["metric_value"],
                "split_by": ["worker_id"],
                "columns": ["other_metric_value"],
            },
            **grouped["panels"],
        },
    }

    in_background(fill)
    record(
        tracker.dashboard_url,
        (WIKI_IMG / "example_perspective_dashboard_layouts.gif",),
        duration=18,
        cues=[(0, click_tab("demo_table")), (5, push_layout(state, grouped)), (11, push_layout(state, charted))],
    )
    tracker.exit()


def scene_task_metadata() -> None:
    """The GCS fields raydar tracks, walked through a group at a time.

    The row is far wider than the viewport and the datagrid does not respond to a
    synthetic horizontal wheel, so the column set is swapped rather than scrolled.
    """
    groups = {
        "Task identity": ["name", "func_or_class_name", "type", "language", "state", "attempt_number", "task_id"],
        "Placement": ["func_or_class_name", "job_id", "node_id", "worker_id", "actor_id", "placement_group_id", "parent_task_id"],
        "Timing and errors": [
            "func_or_class_name",
            "state",
            "creation_time_ms",
            "start_time_ms",
            "end_time_ms",
            "error_type",
            "error_message",
        ],
    }
    layouts = [
        {
            "layout": tab("tasks"),
            "panels": {"tasks": {"table": "task_tracker_data", "plugin": "Datagrid", "title": title, "columns": columns}},
        }
        for title, columns in groups.items()
    ]

    tracker = RayTaskTracker(namespace="raydar-docs", dashboard="local")

    def submit() -> None:
        for round_number in range(16):
            refs = [load_shard.remote(shard) for shard in range(8)]
            refs += [score_batch.remote(batch) for batch in range(round_number * 8, round_number * 8 + 8)]
            tracker.process(refs)

    in_background(submit)
    wait_for_table(tracker, "task_tracker_data")
    state = tracker.dashboard.dashboard.state
    state.layout = layouts[0]
    record(
        tracker.dashboard_url,
        (WIKI_IMG / "example_task_metadata.gif",),
        duration=18,
        cues=[(6, push_layout(state, layouts[1])), (12, push_layout(state, layouts[2]))],
        follow=True,
    )
    tracker.exit()


def scene_custom_metrics() -> None:
    """The wiki's per-node training metrics: a table a training loop writes into, charted live.

    On a single-node dev cluster `node_id` has one value, so the chart splits on
    the metric name too rather than showing a lone series.
    """
    layout = {
        "layout": split("vertical", [0.6, 0.4], tab("loss"), tab("metrics")),
        "panels": {
            "loss": {
                "table": "metrics_table",
                "plugin": "Y Line",
                "title": "Loss per node",
                "group_by": ["timestamp"],
                "split_by": ["node_id", "metric_name"],
                "columns": ["value"],
            },
            "metrics": {
                "table": "metrics_table",
                "plugin": "Datagrid",
                "title": "metrics_table",
                "sort": [["timestamp", "desc"]],
            },
        },
    }
    tracker = RayTaskTracker(namespace="raydar-docs", dashboard="local", dashboard_options={"layout": layout})
    tracker.create_table(
        "metrics_table",
        {"node_id": "string", "metric_name": "string", "value": "float", "timestamp": "datetime"},
    )

    def train() -> None:
        for epoch in range(1, 60):
            tracker.update_table("metrics_table", ray.get(training_epoch.remote(epoch)))

    in_background(train)
    record(tracker.dashboard_url, (WIKI_IMG / "example_custom_metrics.gif",), duration=16)
    tracker.exit()


SCENES = {
    "ml": scene_ml,
    "dashboard": scene_dashboard,
    "custom-table": scene_custom_table,
    "layouts": scene_layouts,
    "task-metadata": scene_task_metadata,
    "custom-metrics": scene_custom_metrics,
}


def main(names: list[str]) -> int:
    unknown = [name for name in names if name not in SCENES]
    if unknown:
        print(f"unknown scene(s): {', '.join(unknown)}\navailable: {', '.join(SCENES)}", file=sys.stderr)
        return 2

    random.seed(20240201)
    # The task-metadata scenes raise on purpose; the tracker never consumes the errors.
    os.environ["RAY_IGNORE_UNHANDLED_ERRORS"] = "1"
    ray.init(logging_level="error")
    try:
        for name in names or SCENES:
            print(f"recording {name}")
            SCENES[name]()
    finally:
        ray.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
