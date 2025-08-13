import os
import subprocess
import re
from pathlib import Path
from tqdm import tqdm

def is_already_converted(mov_path: Path) -> bool:
    mp4_path = mov_path.with_suffix('.mp4')
    return mp4_path.exists()

def convert_to_plex_optimized(input_path: Path):
    output_path = input_path.with_suffix('.mp4')
    print(f"🎞️ Converting to Plex optimized: {input_path.name}")

    # Get duration in seconds
    probe = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of',
         'default=noprint_wrappers=1:nokey=1', str(input_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    duration = float(probe.stdout.strip())

    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-c:v", "libx265",
        "-preset", "slow",
        "-crf", "23",
        "-vf", "scale=720:480,setsar=8/9,format=yuv420p",
        "-pix_fmt", "yuv420p",
        "-tag:v", "hvc1",
        "-c:a", "aac",
        "-b:a", "160k",
        "-y",
        str(output_path)
    ]

    process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)
    pattern = re.compile(r'time=(\d+:\d+:\d+\.\d+)')
    pbar = tqdm(total=duration, unit='s', desc=output_path.name, dynamic_ncols=True)

    def hms_to_sec(hms):
        h, m, s = hms.split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)

    for line in process.stderr:
        match = pattern.search(line)
        if match:
            current_time = hms_to_sec(match.group(1))
            pbar.n = min(current_time, duration)
            pbar.refresh()

    process.wait()
    pbar.n = duration
    pbar.refresh()
    pbar.close()

    if process.returncode == 0:
        print(f"✅ Created: {output_path.name}")
    else:
        print(f"❌ Failed to create: {output_path.name}")

def find_and_convert_movs(root_dir: Path):
    mov_files = []

    clips_dir = root_dir / "clips"
    if not clips_dir.exists():
        print("❌ Clips directory not found.")
        return

    # Collect .mov files directly in clips/
    mov_files.extend([p for p in clips_dir.glob("*.mov")])

    # Collect .mov files in clips/*/finals/
    for scene_dir in clips_dir.iterdir():
        if scene_dir.is_dir():
            finals_dir = scene_dir / "finals"
            if finals_dir.exists():
                mov_files.extend([p for p in finals_dir.glob("*.mov")])

    if not mov_files:
        print("ℹ️ No .mov files found to convert.")
        return

    for mov in mov_files:
        if not is_already_converted(mov):
            convert_to_plex_optimized(mov)
        else:
            print(f"⏩ Already exists: {mov.with_suffix('.mp4').name}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python make_plex_file.py /path/to/input_folder")
        sys.exit(1)

    source_dir = Path(sys.argv[1])
    find_and_convert_movs(source_dir)