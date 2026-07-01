from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SCENARIOS = [
    {
        "kind": "normal_cooking",
        "title": "测试视频：家常菜教学",
        "description": "一条普通做饭教学视频，语气平和，适合通过审核。",
    },
    {
        "kind": "normal_travel",
        "title": "测试视频：城市旅行记录",
        "description": "一条普通旅行短视频，展示街景和地标。",
    },
    {
        "kind": "education",
        "title": "测试视频：课程片段",
        "description": "一条普通教育内容，用于测试低风险机审。",
    },
    {
        "kind": "marketing_qr",
        "title": "测试视频：扫码领取优惠",
        "description": "画面提示 scan QR code 领取 bonus，用于测试导流和营销风险。",
    },
    {
        "kind": "betting",
        "title": "测试视频：betting bonus 宣传",
        "description": "内容包含 betting bonus 和 gambling 相关词，用于测试 block 建议。",
    },
]

PLACEHOLDER_PREFIX = b"VGP_PLACEHOLDER_MEDIA_FIXTURE\n"


def ffmpeg_command(ffmpeg_bin: str, index: int, target: Path, duration: float) -> list[str]:
    hue = (index * 37) % 360
    return [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=640x360:rate=25:duration={duration}",
        "-vf",
        f"hue=h={hue}",
        "-an",
        # H.264 + yuv420p so the clips play in every standard player
        # (Windows Media Player / 电影和电视, browsers, VLC, etc.)
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-movflags",
        "+faststart",
        str(target),
    ]


def write_placeholder(target: Path, index: int, scenario: dict[str, str]) -> None:
    body = {
        "index": index,
        "note": "ffmpeg was not available; this is a small placeholder media fixture for ingestion/load tests.",
        "scenario": scenario,
    }
    target.write_bytes(PLACEHOLDER_PREFIX + json.dumps(body, ensure_ascii=False).encode("utf-8"))


def generate_file(
    target: Path,
    index: int,
    scenario: dict[str, str],
    duration: float,
    ffmpeg_bin: str,
) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if ffmpeg_bin:
        completed = subprocess.run(
            ffmpeg_command(ffmpeg_bin, index, target, duration),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0 and target.exists() and target.stat().st_size > 0:
            return "mp4"
    write_placeholder(target, index, scenario)
    return "placeholder"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate local video fixtures for bulk ingestion tests.")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "test_videos"))
    parser.add_argument("--duration", type=float, default=1.0)
    parser.add_argument("--ffmpeg-bin", default=os.environ.get("VGP_FFMPEG_PATH", ""))
    args = parser.parse_args()

    if args.count <= 0:
        raise SystemExit("--count must be positive")
    output_dir = Path(args.output_dir).resolve()
    ffmpeg_bin = args.ffmpeg_bin or shutil.which("ffmpeg") or ""

    manifest = []
    mode_counts = {"mp4": 0, "placeholder": 0}
    for index in range(args.count):
        scenario = SCENARIOS[index % len(SCENARIOS)]
        filename = f"{index:05d}_{scenario['kind']}.mp4"
        path = output_dir / filename
        mode = generate_file(path, index, scenario, args.duration, ffmpeg_bin)
        mode_counts[mode] += 1
        manifest.append(
            {
                "title": f"{scenario['title']} #{index:05d}",
                "description": scenario["description"],
                "creator_id": f"creator_load_{index % 20:02d}",
                "poi": "global",
                "video_url": str(path),
                "fixture_mode": mode,
                "fixture_kind": scenario["kind"],
            }
        )

    manifest_path = output_dir / "manifest.json"
    batch_path = output_dir / "batch_items.json"
    manifest_path.write_text(json.dumps({"items": manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
    batch_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "count": args.count,
                "ffmpeg_available": bool(ffmpeg_bin),
                "ffmpeg_bin": ffmpeg_bin,
                "generated": mode_counts,
                "manifest": str(manifest_path),
                "batch_items": str(batch_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
