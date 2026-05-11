"""Headless CLI for the same use cases the GUI exposes."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.bootstrap.container import Container
from src.bootstrap.inference_config import InferenceConfig
from src.bootstrap.paths import DEFAULT_DATA_DIR, DEFAULT_RESULT_DIR
from src.domain.entities.roi_config import ROIConfig
from src.domain.value_objects import CountingLine, LineDirection, ROIPolygon, apply_pce_overrides


def _parse_points(text: str) -> list[tuple[int, int]]:
    parts = [p for p in text.split(";") if p.strip()]
    out: list[tuple[int, int]] = []
    for p in parts:
        x, y = p.split(",")
        out.append((int(x), int(y)))
    return out


def cmd_add_source(container: Container, args) -> int:
    src = container.data_management_service().add_source(args.name, args.path)
    print(src.id)
    return 0


def cmd_list_sources(container: Container, args) -> int:
    for s in container.data_management_service().list_sources():
        print(f"{s.id}\t{s.name}\t{s.path}")
    return 0


def cmd_set_roi(container: Container, args) -> int:
    polygons: list[ROIPolygon] = []
    if args.polygon:
        for i, polytext in enumerate(args.polygon):
            polygons.append(ROIPolygon.from_points(f"zone_{i + 1}", _parse_points(polytext)))
    lines: list[CountingLine] = []
    if args.line:
        for i, line in enumerate(args.line):
            pts = _parse_points(line)
            if len(pts) != 2:
                raise SystemExit(f"--line must have exactly 2 points: {line}")
            lines.append(
                CountingLine(
                    f"line_{i + 1}",
                    start=pts[0],
                    end=pts[1],
                    direction=LineDirection.BOTH,
                )
            )
    cfg = ROIConfig(
        source_id=args.source_id,
        roi_polygons=polygons,
        counting_lines=lines,
        pixels_per_meter=args.pixels_per_meter,
    )
    container.roi_config_service().save_config(cfg)
    print("OK")
    return 0


def cmd_run(container: Container, args) -> int:
    meta = container.video_reader.get_metadata(
        container.source_repo.get(args.source_id).path
    )
    service = container.analysis_service(frame_rate=int(meta.fps) or 30)
    session = service.start_session(args.source_id, interval_seconds=args.interval)
    service.run_session(
        session.id,
        progress_cb=lambda p: print(
            f"[{p.intervals_completed} intervals] frame {p.current_frame}/{p.total_frames}",
            file=sys.stderr,
        ),
        annotated_output_path=args.output,
    )
    print(session.id)
    return 0


def cmd_preview(container: Container, args) -> int:
    """Render a time-slice of the video as annotated PNGs for visual inspection."""
    import cv2

    meta = container.video_reader.get_metadata(
        container.source_repo.get(args.source_id).path
    )
    viz = container.visualization_service(frame_rate=int(meta.fps) or 30)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    views = viz.preview_slice(args.source_id, args.start, args.end)
    for v in views:
        cv2.imwrite(str(out_dir / f"frame_{v.frame_index:05d}.png"), v.frame)
        print(
            f"frame {v.frame_index}: {len(v.detections)} detections | "
            + ", ".join(
                f"#{d['tracker_id']} {d['class_name']} {d['confidence']:.2f}"
                for d in v.detections
                if d['class_name'] is not None
            )
        )
    print(f"saved {len(views)} frames to {out_dir}")
    return 0


def cmd_render(container: Container, args) -> int:
    """Run detection + tracking on the whole video and save an annotated mp4 with ROI overlay."""
    meta = container.video_reader.get_metadata(
        container.source_repo.get(args.source_id).path
    )
    viz = container.visualization_service(frame_rate=int(meta.fps) or 30)
    out = viz.render_full_video(
        args.source_id,
        args.output,
        progress_cb=lambda p: print(
            f"frame {p.current_frame}/{p.total_frames}",
            file=sys.stderr,
        ),
    )
    print(out)
    return 0


def _resolve_frame_index(container: Container, args) -> int:
    """Convert --frame or --time into an absolute frame index."""
    if args.frame is not None and args.time is not None:
        raise SystemExit("Specify either --frame or --time, not both")
    if args.frame is not None:
        return int(args.frame)
    if args.time is not None:
        meta = container.video_reader.get_metadata(
            container.source_repo.get(args.source_id).path
        )
        if meta.fps <= 0:
            raise SystemExit("Cannot resolve --time: video reports invalid fps")
        return int(round(float(args.time) * meta.fps))
    return 0


def cmd_extract_frame(container: Container, args) -> int:
    """Extract a single frame and save as PNG for inspection (Luồng 1b)."""
    svc = container.frame_extraction_service()
    idx = _resolve_frame_index(container, args)
    frame = svc.extract_frame(args.source_id, idx)
    path = svc.save_frame(frame, args.source_id, idx)
    print(path)
    return 0


def cmd_monitor(container: Container, args) -> int:
    """One-shot dump of CPU/RAM/GPU usage."""
    snap = container.system_monitor().snapshot()
    print(f"CPU: {snap.cpu_percent:.1f}%")
    print(f"RAM: {snap.ram_percent:.1f}% ({snap.ram_used_mb:,.0f} / {snap.ram_total_mb:,.0f} MB)")
    if not snap.gpus:
        print("GPU: không có CUDA")
        return 0
    for g in snap.gpus:
        util = f"{g.utilization_percent:.1f}%" if g.utilization_percent is not None else "N/A"
        print(
            f"GPU[{g.index}] {g.name}: util {util}, "
            f"VRAM {g.memory_used_mb:,.0f} / {g.memory_total_mb:,.0f} MB"
        )
    return 0


def cmd_test_detect(container: Container, args) -> int:
    """Run a one-shot test detection on a single frame and save annotated PNG (Luồng 1b)."""
    import cv2

    svc = container.frame_extraction_service()
    idx = _resolve_frame_index(container, args)
    result = svc.run_test_detection(args.source_id, idx)

    out_path = Path(args.output) if args.output else (
        Path(container.data_dir) / "frames" / f"test_detect_{args.source_id}_{idx:06d}.png"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out_path), result.annotated_frame):
        raise SystemExit(f"Failed to write {out_path}")

    print(f"frame_index: {idx}")
    print(f"detections : {len(result.detections)}")
    if result.counts_by_class:
        for cls, n in sorted(result.counts_by_class.items()):
            print(f"  {cls}: {n}")
    print(out_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="traffic-analysis")
    parser.add_argument(
        "--data-dir", default=str(DEFAULT_DATA_DIR)
    )
    parser.add_argument(
        "--weights",
        default=None,
        help="Path tới YOLO weights; override model.weights trong inference config",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path tới file YAML cấu hình inference (mặc định: config/inference.yaml)",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Override model.device: 'cpu', 'cuda:0', 'mps' (mặc định: theo cấu hình YAML)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add-source")
    p_add.add_argument("name")
    p_add.add_argument("path")
    p_add.set_defaults(func=cmd_add_source)

    p_list = sub.add_parser("list-sources")
    p_list.set_defaults(func=cmd_list_sources)

    p_roi = sub.add_parser("set-roi")
    p_roi.add_argument("source_id")
    p_roi.add_argument("--polygon", action="append", help="x,y;x,y;x,y...")
    p_roi.add_argument("--line", action="append", help="x,y;x,y")
    p_roi.add_argument("--pixels-per-meter", type=float, default=0.0)
    p_roi.set_defaults(func=cmd_set_roi)

    p_run = sub.add_parser("run")
    p_run.add_argument("source_id")
    p_run.add_argument(
        "--interval",
        type=float,
        default=None,
        help="Độ dài interval (giây); mặc định lấy từ analysis.default_interval_seconds trong config",
    )
    p_run.add_argument("--output", default=None, help="optional annotated video output path")
    p_run.set_defaults(func=cmd_run)

    p_preview = sub.add_parser(
        "preview",
        help="Render a slice [start,end) of the video as annotated PNGs for inspection",
    )
    p_preview.add_argument("source_id")
    p_preview.add_argument("--start", type=int, default=0)
    p_preview.add_argument("--end", type=int, default=30)
    p_preview.add_argument(
        "--out-dir",
        default=str(DEFAULT_RESULT_DIR / "preview"),
        help="directory to save PNGs (mặc định: <project_root>/result/preview)",
    )
    p_preview.set_defaults(func=cmd_preview)

    p_render = sub.add_parser(
        "render",
        help="Run detection on the whole video and save annotated mp4 (with ROI overlay)",
    )
    p_render.add_argument("source_id")
    p_render.add_argument(
        "--output",
        default=str(DEFAULT_RESULT_DIR / "annotated.mp4"),
        help="đường dẫn file mp4 output (mặc định: <project_root>/result/annotated.mp4)",
    )
    p_render.set_defaults(func=cmd_render)

    p_extract = sub.add_parser(
        "extract-frame",
        help="Extract a single frame and save as PNG (Luồng 1b)",
    )
    p_extract.add_argument("source_id")
    p_extract.add_argument("--frame", type=int, help="frame index")
    p_extract.add_argument("--time", type=float, help="timestamp in seconds")
    p_extract.set_defaults(func=cmd_extract_frame)

    p_monitor = sub.add_parser(
        "monitor",
        help="In trạng thái CPU/RAM/GPU hiện tại (one-shot)",
    )
    p_monitor.set_defaults(func=cmd_monitor)

    p_test = sub.add_parser(
        "test-detect",
        help="Run one-shot detection on a single frame, save annotated PNG (Luồng 1b)",
    )
    p_test.add_argument("source_id")
    p_test.add_argument("--frame", type=int, help="frame index")
    p_test.add_argument("--time", type=float, help="timestamp in seconds")
    p_test.add_argument("--output", default=None, help="annotated PNG output path")
    p_test.set_defaults(func=cmd_test_detect)

    args = parser.parse_args(argv)

    config = InferenceConfig.load(args.config)
    apply_pce_overrides(config.vehicle_pce.as_mapping())

    weights_override: str | None = None
    if args.weights:
        weights_override = args.weights if Path(args.weights).exists() else args.weights

    container = Container(
        data_dir=Path(args.data_dir),
        inference_config=config,
        weights_path=weights_override,
    )
    if args.device:
        container.set_device_override(args.device)
    return args.func(container, args)


if __name__ == "__main__":
    raise SystemExit(main())
