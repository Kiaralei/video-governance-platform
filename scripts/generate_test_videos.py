from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Each scenario burns real, on-screen content into the video so the moderation
# pipeline's OCR / vision path (Azure Vision or another detector) can extract
# meaningful signals from the extracted keyframes -- not just the title text.
#   headline  : big English line (kept in English so keyword detection fires)
#   keywords  : detection keywords drawn on screen (match model_gateway tags)
#   qr        : when true, a scannable QR code is composited into the frame
SCENARIOS = [
    {
        "kind": "normal_cooking",
        "title": "测试视频：家常菜教学",
        "description": "一条普通做饭教学视频，语气平和，适合通过审核。",
        "headline": "HOME COOKING TUTORIAL",
        "keywords": "recipe . kitchen . food",
        "qr": False,
        "accent": (46, 160, 67),
    },
    {
        "kind": "normal_travel",
        "title": "测试视频：城市旅行记录",
        "description": "一条普通旅行短视频，展示街景和地标。",
        "headline": "CITY TRAVEL VLOG",
        "keywords": "travel . city . hotel",
        "qr": False,
        "accent": (31, 111, 235),
    },
    {
        "kind": "education",
        "title": "测试视频：课程片段",
        "description": "一条普通教育内容，用于测试低风险机审。",
        "headline": "ONLINE COURSE LESSON",
        "keywords": "tutorial . lesson . education",
        "qr": False,
        "accent": (137, 87, 229),
    },
    {
        "kind": "marketing_qr",
        "title": "测试视频：扫码领取优惠",
        "description": "画面提示 scan QR code 领取 bonus，用于测试导流和营销风险。",
        "headline": "SCAN QR CODE FOR BONUS",
        "keywords": "scan . qr code . bonus . promo",
        "qr": True,
        "accent": (219, 109, 40),
    },
    {
        "kind": "betting",
        "title": "测试视频：betting bonus 宣传",
        "description": "内容包含 betting bonus 和 gambling 相关词，用于测试 block 建议。",
        "headline": "BETTING BONUS",
        "keywords": "betting . gambling . casino . bet",
        "qr": False,
        "accent": (207, 34, 46),
    },
]

PLACEHOLDER_PREFIX = b"VGP_PLACEHOLDER_MEDIA_FIXTURE\n"

FRAME_W, FRAME_H = 640, 360

FONT_CANDIDATES_EN = [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"]
FONT_CANDIDATES_CJK = [r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]


def _load_font(candidates: list[str], size: int):
    from PIL import ImageFont

    for path in candidates:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_centered(draw, cx: int, y: int, text: str, font, fill) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text((cx - (right - left) / 2, y), text, font=font, fill=fill)


def render_overlay(scenario: dict, target_png: Path) -> None:
    """Render a full-frame RGBA overlay (text + optional QR) for one scenario."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_cjk = _load_font(FONT_CANDIDATES_CJK, 30)
    font_headline = _load_font(FONT_CANDIDATES_EN, 40)
    font_keywords = _load_font(FONT_CANDIDATES_EN, 24)

    # Top ribbon with the Chinese scenario title.
    draw.rectangle([0, 0, FRAME_W, 52], fill=(0, 0, 0, 170))
    draw.text((16, 10), scenario["title"], font=font_cjk, fill=(255, 255, 255, 255))

    # Bottom panel with the English headline + detection keywords.
    draw.rectangle([0, FRAME_H - 110, FRAME_W, FRAME_H], fill=(0, 0, 0, 175))
    accent = tuple(scenario["accent"]) + (255,)
    _draw_centered(draw, FRAME_W // 2, FRAME_H - 96, scenario["headline"], font_headline, accent)
    _draw_centered(draw, FRAME_W // 2, FRAME_H - 44, scenario["keywords"], font_keywords, (255, 214, 10, 255))

    if scenario.get("qr"):
        import qrcode

        qr_payload = "https://promo.example.com/bonus?ref=vgp_test"
        qr_img = qrcode.make(qr_payload).convert("RGBA").resize((150, 150), Image.NEAREST)
        # White quiet-zone card behind the QR so it stays scannable over the pattern.
        card = Image.new("RGBA", (166, 166), (255, 255, 255, 255))
        card.paste(qr_img, (8, 8))
        img.alpha_composite(card, (FRAME_W - 182, 66))

    target_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(target_png)


def ffmpeg_command(ffmpeg_bin: str, index: int, overlay_png: Path, target: Path, duration: float) -> list[str]:
    hue = (index * 37) % 360
    # Convert the full-range (pc) testsrc2 signal to limited/tv range, matching
    # real delivered H.264 -- otherwise downstream mjpeg keyframe extraction
    # rejects the frames with "Non full-range YUV is non-standard".
    filtergraph = (
        f"[0:v]hue=h={hue}[bg];"
        f"[bg][1:v]overlay=0:0:format=auto,"
        f"scale=w={FRAME_W}:h={FRAME_H}:in_range=full:out_range=tv,"
        f"format=yuv420p[v]"
    )
    return [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size={FRAME_W}x{FRAME_H}:rate=25:duration={duration}",
        "-i",
        str(overlay_png),
        "-filter_complex",
        filtergraph,
        "-map",
        "[v]",
        "-an",
        "-color_range",
        "tv",
        # H.264 + yuv420p so the clips play in every standard player.
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-movflags",
        "+faststart",
        str(target),
    ]


def write_placeholder(target: Path, index: int, scenario: dict) -> None:
    body = {
        "index": index,
        "note": "ffmpeg was not available; this is a small placeholder media fixture for ingestion/load tests.",
        "scenario": {k: scenario[k] for k in ("kind", "title", "description")},
    }
    target.write_bytes(PLACEHOLDER_PREFIX + json.dumps(body, ensure_ascii=False).encode("utf-8"))


def generate_file(
    target: Path,
    index: int,
    scenario: dict,
    overlay_png: Path | None,
    duration: float,
    ffmpeg_bin: str,
) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if ffmpeg_bin and overlay_png is not None:
        completed = subprocess.run(
            ffmpeg_command(ffmpeg_bin, index, overlay_png, target, duration),
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
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "test_videos"))
    # ~20s matches real short-form content and clears the pipeline's fps=1/15
    # keyframe cadence (a 3s clip yields zero extractable frames).
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--ffmpeg-bin", default=os.environ.get("VGP_FFMPEG_PATH", ""))
    args = parser.parse_args()

    if args.count <= 0:
        raise SystemExit("--count must be positive")
    output_dir = Path(args.output_dir).resolve()
    ffmpeg_bin = args.ffmpeg_bin or shutil.which("ffmpeg") or ""

    # Pre-render one overlay per scenario kind and reuse it across every clip of
    # that kind (only the background hue varies per index).
    overlay_dir = Path(tempfile.mkdtemp(prefix="vgp_overlays_"))
    overlays: dict[str, Path] = {}
    if ffmpeg_bin:
        for scenario in SCENARIOS:
            png = overlay_dir / f"{scenario['kind']}.png"
            render_overlay(scenario, png)
            overlays[scenario["kind"]] = png

    manifest = []
    mode_counts = {"mp4": 0, "placeholder": 0}
    try:
        for index in range(args.count):
            scenario = SCENARIOS[index % len(SCENARIOS)]
            filename = f"{index:05d}_{scenario['kind']}.mp4"
            path = output_dir / filename
            overlay_png = overlays.get(scenario["kind"])
            mode = generate_file(path, index, scenario, overlay_png, args.duration, ffmpeg_bin)
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
    finally:
        shutil.rmtree(overlay_dir, ignore_errors=True)

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
