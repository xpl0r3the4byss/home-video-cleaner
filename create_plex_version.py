#!/usr/bin/env python3
import sys
import subprocess
import json
from pathlib import Path
from typing import Tuple

def verbose_log(msg: str):
    print(msg, file=sys.stderr)

def get_display_resolution(mov_file: Path, choice: str) -> Tuple[int, int]:
    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,display_aspect_ratio,sample_aspect_ratio",
        "-of", "json",
        str(mov_file)
    ]
    try:
        result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        info = json.loads(result.stdout)
        stream = info["streams"][0]
        sar = stream.get("sample_aspect_ratio", "1:1")
        width = stream.get("width", 720)
        height = stream.get("height", 480)
        num, den = map(int, sar.split(":"))
        if den == 0:
            return width, height  # fallback
        par = num / den
        dar = (width * par) / height
        # Override with user-provided aspect choice
        if choice == "A":
            return 640, 480  # 4:3
        elif choice == "B":
            return 854, 480  # anamorphic 16:9
        else:
            return 640, 480  # fallback to 4:3 if invalid
    except Exception as e:
        verbose_log(f"⚠️ ffprobe failed on {mov_file}: {e}")
        return 720, 480

def get_duration_seconds(mov_file: Path) -> float:
    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(mov_file)
    ]
    try:
        result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        duration_str = result.stdout.strip()
        return float(duration_str)
    except Exception as e:
        verbose_log(f"⚠️ ffprobe failed to get duration on {mov_file}: {e}")
        return 1.0

def create_plex_version(input_file: Path, choice: str = "A", max_retries: int = 3) -> Path:
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # Output path will be next to input with .mp4 extension
    plex_output_path = input_file.with_suffix(".mp4")
    out_width, out_height = get_display_resolution(input_file, choice)
    duration_in_seconds = get_duration_seconds(input_file)

    ffmpeg_command = [
        "ffmpeg",
        "-i", str(input_file),
        "-vf", f"scale={out_width}:{out_height}",
        "-c:v", "libx265",
        "-pix_fmt", "yuv420p",
        "-tag:v", "hvc1",
        "-crf", "23",
        "-preset", "slow",
        "-c:a", "aac",
        "-b:a", "192k",
        "-progress", "pipe:1",
        "-nostats",
        str(plex_output_path)
    ]

    retry_count = 0
    success = False

    while retry_count < max_retries and not success:
        try:
            verbose_log(f"🎞️ Converting to Plex version (attempt {retry_count + 1}/{max_retries})")
            proc = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
            
            for line in proc.stdout:
                if line.startswith("out_time="):
                    val = line.strip().split('=')[1]
                    try:
                        h, m, s = val.split(':')
                        sec = float(h) * 3600 + float(m) * 60 + float(s)
                        percent = (sec / duration_in_seconds) * 100
                        print(f"\rProgress: {percent:.1f}%", end='', flush=True)
                    except Exception:
                        pass

            proc.wait()
            print()  # New line after progress

            if proc.returncode == 0 and plex_output_path.exists() and plex_output_path.stat().st_size > 0:
                verbose_log(f"✅ Created Plex-optimized version: {plex_output_path}")
                success = True
            else:
                retry_count += 1
                if retry_count < max_retries:
                    verbose_log(f"⚠️ Conversion failed, retrying ({retry_count}/{max_retries})")
                else:
                    verbose_log(f"❌ Conversion failed after {max_retries} attempts")
                    raise Exception(f"Failed to create Plex version after {max_retries} attempts")

        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                verbose_log(f"⚠️ Error during conversion, retrying ({retry_count}/{max_retries}): {e}")
                continue
            verbose_log(f"❌ Error during conversion after {max_retries} attempts: {e}")
            raise

    return plex_output_path

def main():
    if len(sys.argv) < 2:
        print("Usage: python create_plex_version.py <input_file> [aspect_ratio]")
        print("Aspect ratio options:")
        print("   A) 4:3 (default)")
        print("   B) Anamorphic 16:9")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    choice = sys.argv[2].upper() if len(sys.argv) > 2 else "A"

    if choice not in ["A", "B"]:
        print("Invalid aspect ratio choice. Using default (4:3)")
        choice = "A"

    try:
        plex_path = create_plex_version(input_path, choice)
        print(f"\nPlex version created successfully: {plex_path}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()