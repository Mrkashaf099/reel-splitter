#!/usr/bin/env python3
"""
reel_splitter.py
Fit a 16:9 video into a 9:16 frame (black or white background),
split it into equal parts, and stamp the title on top and "Part-N" below.

Needs: python3, ffmpeg, ffprobe (with the drawtext filter)

Example:
  python3 reel_splitter.py my_video.mp4 --title "My Video Name"
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys

DEFAULT_FONTS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "DejaVuSans-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]


def probe(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "json", path,
    ])
    data = json.loads(out)
    st = data["streams"][0]
    return int(st["width"]), int(st["height"]), float(data["format"]["duration"])


def find_font(user_font):
    if user_font:
        return user_font
    for f in DEFAULT_FONTS:
        if os.path.exists(f):
            return f
    sys.exit("No font found. Install one (sudo apt install fonts-dejavu-core) "
             "or pass --font /path/to/font.ttf")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="input video file")
    ap.add_argument("--title", required=True, help="text shown on top of every part")
    ap.add_argument("--part-seconds", type=int, default=60, help="length of each part (default 60)")
    ap.add_argument("--width", type=int, default=1080,
                    help="output width; height is width*16/9 (1080 or 720)")
    ap.add_argument("--bg", default="black", choices=["black", "white"], help="background colour")
    ap.add_argument("--start-part", type=int, default=1, help="number of the first part (default 1)")
    ap.add_argument("--label", default="Part-", help='label before the number (default "Part-")')
    ap.add_argument("--outdir", default="parts", help="output folder")
    ap.add_argument("--preset", default="veryfast", help="x264 preset (ultrafast = fastest)")
    ap.add_argument("--crf", type=int, default=23, help="quality, lower is better (default 23)")
    ap.add_argument("--font", default=None, help="path to a .ttf font")
    ap.add_argument("--zip", action="store_true", help="also make a zip of all parts")
    args = ap.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found. Install ffmpeg first.")

    font = find_font(args.font)
    iw, ih, duration = probe(args.input)

    W = args.width - args.width % 2
    H = (W * 16 // 9) // 2 * 2
    vh = round(W * ih / iw / 2) * 2          # height of the scaled video
    if vh > H:
        sys.exit("Video is taller than 9:16; this tool expects wide (16:9) footage.")
    band = (H - vh) // 2                      # empty band above and below the video

    fg = "white" if args.bg == "black" else "black"
    title_size = max(20, min(W // 12, int(W * 0.9 / (0.62 * max(1, len(args.title))))))
    part_size = W // 10

    os.makedirs(args.outdir, exist_ok=True)
    total = math.ceil(duration / args.part_seconds)
    print(f"Video {iw}x{ih}, {duration/60:.1f} min -> {total} parts of {args.part_seconds}s, "
          f"output {W}x{H}")

    title_file = os.path.join(args.outdir, ".title.txt")
    with open(title_file, "w", encoding="utf-8") as f:
        f.write(args.title)

    made = []
    for i in range(total):
        num = args.start_part + i
        start = i * args.part_seconds
        length = min(args.part_seconds, duration - start)
        if length < 1:
            continue
        out = os.path.join(args.outdir, f"part_{num:03d}.mp4")
        if os.path.exists(out) and os.path.getsize(out) > 0:
            print(f"[{i+1}/{total}] {out} exists, skipping")
            made.append(out)
            continue

        part_file = os.path.join(args.outdir, ".part.txt")
        with open(part_file, "w", encoding="utf-8") as f:
            f.write(f"{args.label}{num}")

        vf = (
            f"scale={W}:{vh},"
            f"pad={W}:{H}:0:{band}:color={args.bg},"
            f"drawtext=fontfile='{font}':textfile='{title_file}':fontcolor={fg}:"
            f"fontsize={title_size}:x=(w-text_w)/2:y=({band}-text_h)/2,"
            f"drawtext=fontfile='{font}':textfile='{part_file}':fontcolor={fg}:"
            f"fontsize={part_size}:x=(w-text_w)/2:y={band + vh}+({band}-text_h)/2,"
            f"setsar=1,format=yuv420p"
        )
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error", "-stats",
            "-ss", str(start), "-t", str(length), "-i", args.input,
            "-map", "0:v:0", "-map", "0:a:0?",
            "-vf", vf,
            "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", out,
        ]
        print(f"[{i+1}/{total}] making {out}")
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            if os.path.exists(out):
                os.remove(out)
            sys.exit(f"ffmpeg failed on part {num}. Run again; finished parts are skipped.")
        made.append(out)

    for tmp in (title_file, os.path.join(args.outdir, ".part.txt")):
        if os.path.exists(tmp):
            os.remove(tmp)

    if args.zip:
        z = shutil.make_archive(args.outdir, "zip", args.outdir)
        print(f"Zip: {z}")
    print(f"Done: {len(made)} parts in {args.outdir}/")


if __name__ == "__main__":
    main()
