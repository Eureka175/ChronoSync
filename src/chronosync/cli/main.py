"""ChronoSync command-line interface.

Commands::

    chronosync info <file> [--json]
    chronosync gcc <reference> <target> [--search-min N] [--search-max N]
                   [--max-seconds S] [--json]
    chronosync align <reference> <target> [--json] [--sesx OUT.sesx]
                     [--cache-dir DIR] [--max-seconds S]
    chronosync batch <files...> [--json] [--csv OUT.csv] [--sesx OUT.sesx]
    chronosync mp4-sync <files...|--folder DIR> [--fix] [--remux] [--json P]
    chronosync test-gcc
    chronosync benchmark [--suite {gcc,features,drift,all}] [--long] [--json]

All JSON output converts NaN/Inf to ``null`` so it is always valid JSON.
The offset sign convention (ADR-003) applies to every reported value:
``delay = t_target - t_reference``.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

from chronosync import __version__
from chronosync.fine.gcc_phat import GCCResult, gcc_phat
from chronosync.io import probe
from chronosync.models.audio import CANONICAL_SAMPLE_RATE

REPO_ROOT = Path(__file__).resolve().parents[3]


def _sanitize(obj):
    """Convert NaN/Inf to None so serialized output is valid JSON."""
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


def _print_json(obj) -> None:
    print(json.dumps(_sanitize(obj), indent=2, ensure_ascii=False))


# ------------------------------------------------------------------- info


def cmd_info(args: argparse.Namespace) -> int:
    track = probe(args.file)
    data = {
        "name": track.name,
        "path": track.path,
        "sample_rate": track.sample_rate,
        "channels": track.channels,
        "frames": track.frames,
        "duration_seconds": round(track.duration_seconds, 6),
        "format": track.format,
        "subtype": track.subtype,
    }
    if args.json:
        _print_json(data)
    else:
        for key, value in data.items():
            print(f"{key:<18} {value}")
    return 0


# -------------------------------------------------------------------- gcc


def cmd_gcc(args: argparse.Namespace) -> int:
    from chronosync.io import read_canonical

    ref = read_canonical(args.reference, max_seconds=args.max_seconds)
    tgt = read_canonical(args.target, max_seconds=args.max_seconds)
    for label, decoded, path in (("Reference", ref, args.reference), ("Target", tgt, args.target)):
        for warning in decoded.warnings:
            print(f"[{label}] {warning}", file=sys.stderr)

    if ref.mono_mix.size > 30 * 60 * CANONICAL_SAMPLE_RATE:
        print(
            "warning: full-file GCC loads long files into RAM; the chunked "
            "pipeline is planned (see docs/architecture.md)",
            file=sys.stderr,
        )

    result: GCCResult = gcc_phat(
        ref.mono_mix,
        tgt.mono_mix,
        CANONICAL_SAMPLE_RATE,
        search_min=args.search_min,
        search_max=args.search_max,
    )
    data = {
        "reference": str(args.reference),
        "target": str(args.target),
        "sample_rate": CANONICAL_SAMPLE_RATE,
        "method": result.method,
        "status": "success" if result.success else "failure",
        "delay_samples": result.delay_samples,
        "delay_seconds": result.delay_seconds,
        "peak": result.peak_value,
        "second_peak": result.second_peak_value,
        "prominence": result.peak_prominence,
        "confidence": result.confidence,
        "search_range_samples": list(result.search_range_samples),
        "warnings": result.warnings,
    }
    if args.json:
        _print_json(data)
    else:
        print(f"Reference:    {args.reference}")
        print(f"Target:       {args.target}")
        print(f"Method:       {result.method}")
        print(f"Status:       {'success' if result.success else 'failure'}")
        print(f"Delay samples:{result.delay_samples:>15.3f}")
        print(f"Delay seconds:{result.delay_seconds:>15.6f}")
        print(f"Peak:         {result.peak_value:>15.4f}")
        second = result.second_peak_value
        print(f"Second peak:  {(second if second is not None else float('nan')):>15.4f}")
        prom = result.peak_prominence
        print(f"Prominence:   {(prom if prom is not None else float('nan')):>15.4f}")
        print(f"Confidence:   {result.confidence:>15.4f}")
        for warning in result.warnings:
            print(f"warning: {warning}", file=sys.stderr)
    return 0


# ------------------------------------------------------------------- align


def cmd_align(args: argparse.Namespace) -> int:
    """Full pipeline: coarse match -> drift estimate -> TimeMap -> export."""
    from chronosync.coarse import coarse_match_paths
    from chronosync.drift import estimate_drift
    from chronosync.export.sesx import clips_from_timemap, write_sesx
    from chronosync.io import read_canonical

    coarse = coarse_match_paths(
        args.reference, args.target, cache_dir=args.cache_dir
    )
    if not coarse.matched:
        data = {
            "reference": args.reference,
            "target": args.target,
            "status": "no_match",
            "coarse": {
                "matched": coarse.matched,
                "method": coarse.method,
                "confidence": coarse.confidence,
                "warnings": coarse.warnings,
            },
        }
        if args.json:
            _print_json(data)
        else:
            print(f"Status:     no_match (best method: {coarse.method}, "
                  f"confidence {coarse.confidence:.3f})")
            for warning in coarse.warnings:
                print(f"warning: {warning}", file=sys.stderr)
        return 1

    ref = read_canonical(args.reference, max_seconds=args.max_seconds)
    tgt = read_canonical(args.target, max_seconds=args.max_seconds)
    est = estimate_drift(
        ref.mono_mix, tgt.mono_mix, CANONICAL_SAMPLE_RATE,
        coarse_offset_samples=coarse.offset_samples,
    )

    data = {
        "reference": args.reference,
        "target": args.target,
        "status": "success" if est.success else "failure",
        "coarse": {
            "matched": coarse.matched,
            "method": coarse.method,
            "offset_samples": coarse.offset_samples,
            "confidence": coarse.confidence,
        },
        "drift": {
            "classification": est.classification,
            "alpha_ppm": est.model.alpha_ppm,
            "beta_samples": est.model.beta_samples,
            "r2": est.model.r2,
            "windows": len(est.measurements),
            "time_map": (est.time_map.to_dict() if est.time_map else None),
            "warnings": est.warnings,
        },
        "sesx": None,
    }

    if est.time_map is not None and args.sesx:
        track = clips_from_timemap(
            args.target, "Target", tgt.mono_mix.size, CANONICAL_SAMPLE_RATE,
            est.time_map,
        )
        write_sesx(args.sesx, [track], CANONICAL_SAMPLE_RATE)
        data["sesx"] = args.sesx

    if args.json:
        _print_json(data)
    else:
        print(f"Status:       {data['status']}")
        print(f"Coarse:       {coarse.method} "
              f"(offset {coarse.offset_samples:.1f} samples, "
              f"confidence {coarse.confidence:.3f})")
        print(f"Drift:        {est.classification} "
              f"(alpha {est.model.alpha_ppm:+.1f} ppm, "
              f"beta {est.model.beta_samples:.1f} samples, "
              f"R2 {est.model.r2:.3f}, {len(est.measurements)} windows)")
        if est.time_map is not None:
            print(f"TimeMap:      {est.time_map.to_dict()}")
        if data["sesx"]:
            print(f"SESX:         {data['sesx']}")
        for warning in est.warnings:
            print(f"warning: {warning}", file=sys.stderr)
    return 0


# ------------------------------------------------------------------- batch


def cmd_batch(args: argparse.Namespace) -> int:
    """Multi-track: all-pairs coarse+drift -> graph solve -> export."""
    from chronosync.export import write_csv, write_sesx
    from chronosync.export.json import track_alignment_to_dict, write_json
    from chronosync.export.sesx import clips_from_timemap
    from chronosync.io import probe
    from chronosync.pipeline import PipelineConfig, batch_align

    cfg = PipelineConfig(cache_dir=args.cache_dir, max_seconds=args.max_seconds)
    result = batch_align(args.files, cfg)
    solved = result.solved

    payload: dict = {
        "status": "success" if solved.success else "failure",
        "reference": solved.reference,
        "tracks": [
            track_alignment_to_dict(t, result.time_maps.get(t.track))
            for t in solved.tracks
        ],
        "warnings": result.warnings,
    }

    if args.csv:
        write_csv(args.csv, solved.tracks, result.time_maps)
        payload["csv"] = args.csv

    if args.sesx:
        sesx_tracks = []
        for track in sorted(result.time_maps):
            tm = result.time_maps[track]
            # find the file path by matching the probed name
            path = next(
                str(p) for p in args.files if probe(p).name == track
            )
            frames = probe(path).frames
            sesx_tracks.append(
                clips_from_timemap(path, track, frames, CANONICAL_SAMPLE_RATE, tm)
            )
        write_sesx(args.sesx, sesx_tracks, CANONICAL_SAMPLE_RATE)
        payload["sesx"] = args.sesx

    if args.json:
        _print_json(payload)
    else:
        print(f"Status:     {payload['status']}")
        print(f"Reference:  {solved.reference}")
        for track in solved.tracks:
            tm = result.time_maps.get(track.track)
            print(
                f"  {track.track:<20} offset {track.offset_samples:>10.1f} samples"
                f"  conf {track.confidence:.3f}  map {tm.kind if tm else '-'}"
            )
        for warning in result.warnings:
            print(f"warning: {warning}", file=sys.stderr)
    return 0


# --------------------------------------------------------------- mp4-sync


def cmd_mp4_sync(args: argparse.Namespace) -> int:
    """Dedicated pipeline: per-file wireless-mic delay measure (+ fix)."""
    import csv as _csv
    import json as _json
    from pathlib import Path as _Path

    from chronosync.mp4sync import process_file, require_ffmpeg

    try:
        require_ffmpeg()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    files = [_Path(f) for f in args.files]
    if args.folder:
        files += sorted(_Path(args.folder).glob("*.MP4"))
    if not files:
        print("no input files", file=sys.stderr)
        return 1

    reports = []
    for path in files:
        print(f"processing {path.name} ...", file=sys.stderr)
        report = process_file(
            path,
            reference_stream=args.reference_stream,
            limit_seconds=args.limit_seconds,
            fix=args.fix,
            out_dir=args.out_dir,
            remux=args.remux,
        )
        reports.append(report)
        for ch in report.channels:
            print(
                f"  stream {ch.stream}: delay {ch.delay_ms:8.3f} ms "
                f"({ch.delay_samples:9.2f} samples) conf {ch.confidence:.2f} "
                f"drift {ch.drift_classification}",
                file=sys.stderr,
            )
        if report.verify_ok is not None:
            print(
                f"  -> fixed: {report.fixed_mp4}  verify max |residual| "
                f"{report.verify_max_abs_ms:.3f} ms "
                f"{'OK' if report.verify_ok else 'FAILED'}",
                file=sys.stderr,
            )

    if args.json:
        _Path(args.json).write_text(
            _json.dumps(
                [r.to_dict() for r in reports], indent=2, ensure_ascii=False
            ),
            encoding="utf-8",
        )
    if args.csv:
        from chronosync.mp4sync import reports_to_csv_rows

        with open(args.csv, "w", encoding="utf-8", newline="") as f:
            _csv.writer(f).writerows(reports_to_csv_rows(reports))

    if args.json is None and args.csv is None:
        for report in reports:
            for ch in report.channels:
                print(
                    f"{report.file}\tstream {ch.stream}\t"
                    f"{ch.delay_ms:.4f} ms\tconf {ch.confidence:.2f}\t"
                    f"{ch.drift_classification}"
                )
    return 0


# --------------------------------------------------------------- test-gcc


def cmd_test_gcc(args: argparse.Namespace) -> int:
    test_file = REPO_ROOT / "tests" / "unit" / "test_gcc_phat.py"
    code = subprocess.call(
        [sys.executable, "-m", "pytest", str(test_file), "-q"], cwd=str(REPO_ROOT)
    )
    return code


# -------------------------------------------------------------- benchmark


def cmd_benchmark(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(REPO_ROOT))
    from benchmarks import benchmark_gcc

    suites = {
        "gcc": benchmark_gcc,
        "features": None,
        "drift": None,
    }
    if args.suite in ("features", "all"):
        from benchmarks import benchmark_features

        suites["features"] = benchmark_features
    if args.suite in ("drift", "all"):
        from benchmarks import benchmark_drift

        suites["drift"] = benchmark_drift
    if args.suite in ("solve", "all"):
        from benchmarks import benchmark_solver

        suites["solve"] = benchmark_solver

    results = []
    if args.suite in ("gcc", "all"):
        results.extend(benchmark_gcc.run(long=args.long))
    if args.suite in ("features", "all"):
        results.extend(suites["features"].run())
    if args.suite in ("drift", "all"):
        results.extend(suites["drift"].run())
    if args.suite in ("solve", "all"):
        results.extend(suites["solve"].run())

    if args.json:
        from benchmarks.common import to_dict

        _print_json([to_dict(r) for r in results])
    else:
        from benchmarks.common import print_table

        print_table(results)
    return 0


# ------------------------------------------------------------------ main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chronosync",
        description="Multi-track audio timebase estimation, alignment and "
        "clock-drift correction (Phase 1: I/O, models, GCC-PHAT).",
    )
    parser.add_argument("--version", action="version", version=f"chronosync {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="print file metadata without decoding")
    p_info.add_argument("file")
    p_info.add_argument("--json", action="store_true")
    p_info.set_defaults(func=cmd_info)

    p_gcc = sub.add_parser("gcc", help="GCC-PHAT delay estimation between two files")
    p_gcc.add_argument("reference")
    p_gcc.add_argument("target")
    p_gcc.add_argument("--search-min", type=int, default=None, help="lower lag bound, samples")
    p_gcc.add_argument("--search-max", type=int, default=None, help="upper lag bound, samples")
    p_gcc.add_argument("--max-seconds", type=float, default=None, help="decode only the first N seconds")
    p_gcc.add_argument("--json", action="store_true")
    p_gcc.set_defaults(func=cmd_gcc)

    p_align = sub.add_parser(
        "align", help="full pipeline: coarse match -> drift -> TimeMap (+ SESX)"
    )
    p_align.add_argument("reference")
    p_align.add_argument("target")
    p_align.add_argument("--sesx", default=None, help="write an Adobe Audition .sesx session")
    p_align.add_argument("--cache-dir", default=None, help="feature cache directory")
    p_align.add_argument("--max-seconds", type=float, default=None,
                         help="decode only the first N seconds (long-file guard)")
    p_align.add_argument("--json", action="store_true")
    p_align.set_defaults(func=cmd_align)

    p_batch = sub.add_parser(
        "batch",
        help="multi-track: all-pairs coarse+drift -> global graph solve -> export",
    )
    p_batch.add_argument("files", nargs="+", help="two or more audio files")
    p_batch.add_argument("--reference", default=None, help="reference track name (default: auto)")
    p_batch.add_argument("--sesx", default=None, help="write an Adobe Audition .sesx session")
    p_batch.add_argument("--csv", default=None, help="write a CSV alignment report")
    p_batch.add_argument("--cache-dir", default=None, help="feature cache directory")
    p_batch.add_argument("--max-seconds", type=float, default=None,
                         help="decode only the first N seconds per file (long-file guard)")
    p_batch.add_argument("--json", action="store_true")
    p_batch.set_defaults(func=cmd_batch)

    p_mp4 = sub.add_parser(
        "mp4-sync",
        help="MP4 wireless-mic delay: measure per-file channel delays "
        "(+ optional --fix/--remux with verification)",
    )
    p_mp4.add_argument("files", nargs="*", help="MP4 files (or use --folder)")
    p_mp4.add_argument("--folder", default=None, help="process every .MP4 in this folder")
    p_mp4.add_argument("--reference-stream", type=int, default=2,
                       help="audio stream used as reference (default 2 = CH3)")
    p_mp4.add_argument("--limit-seconds", type=float, default=120.0,
                       help="measure on the first N seconds")
    p_mp4.add_argument("--fix", action="store_true", help="write delay-corrected audio")
    p_mp4.add_argument("--remux", action="store_true",
                       help="mux the original video with the fixed audio and re-verify")
    p_mp4.add_argument("--out-dir", default=None)
    p_mp4.add_argument("--json", default=None, help="write the JSON report here")
    p_mp4.add_argument("--csv", default=None, help="write a CSV report here")
    p_mp4.set_defaults(func=cmd_mp4_sync)

    p_test = sub.add_parser("test-gcc", help="run the GCC-PHAT unit test suite")
    p_test.set_defaults(func=cmd_test_gcc)

    p_bench = sub.add_parser(
        "benchmark",
        help="run benchmarks (--suite gcc|features|drift|solve|all; --long adds 10 min / 1 h)",
    )
    p_bench.add_argument("--suite", choices=("gcc", "features", "drift", "solve", "all"),
                         default="gcc")
    p_bench.add_argument("--long", action="store_true")
    p_bench.add_argument("--json", action="store_true")
    p_bench.set_defaults(func=cmd_benchmark)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
