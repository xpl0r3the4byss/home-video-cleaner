from config import SCENE_THRESHOLD_HIGH
import subprocess
from pathlib import Path
from typing import List, Tuple
from segment_extractor import extract_segments
from utils import verbose_log

def detect_scene_changes(
    input_file: Path,
    threshold: float = SCENE_THRESHOLD_HIGH
) -> List[float]:
    """
    Run FFmpeg scene detection filter with given threshold on input_file.
    Returns a sorted list of scene change timestamps (seconds).
    """
    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-i", str(input_file),
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null",
        "-"
    ]
    verbose_log(f"Running FFmpeg scene detection with threshold {threshold}:\n{' '.join(cmd)}")

    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True)
    scene_timestamps = []

    for line in proc.stderr:
        if "pts_time:" in line:
            try:
                pts_str = line.split("pts_time:")[1].split(" ")[0]
                timestamp = float(pts_str)
                scene_timestamps.append(timestamp)
            except (IndexError, ValueError):
                continue

    proc.wait()
    verbose_log(f"Detected {len(scene_timestamps)} scene change timestamps")
    scene_timestamps = sorted(set(scene_timestamps))
    return scene_timestamps

def build_scene_segments(
    scene_timestamps: List[float],
    video_duration: float
) -> List[Tuple[float, float]]:
    """
    Given a sorted list of scene timestamps and total duration,
    return a list of (start, end) segments covering the whole video.
    """
    segments = []
    prev = 0.0
    for ts in scene_timestamps:
        segments.append((prev, ts))
        prev = ts
    if prev < video_duration:
        segments.append((prev, video_duration))
    verbose_log(f"Built {len(segments)} scene segments")
    return segments

def get_video_duration(input_file: Path) -> float:
    """
    Uses ffprobe to get the duration of the video in seconds.
    """
    import json
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "json",
        str(input_file)
    ]
    verbose_log(f"Running ffprobe to get video duration:\n{' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {input_file}")
    info = json.loads(result.stdout)
    duration = float(info["format"]["duration"])
    verbose_log(f"Video duration: {duration} seconds")
    return duration

def split_clip_on_scenes(
    input_file: Path,
    output_dir: Path,
    prefix: str,
    threshold: float = SCENE_THRESHOLD_HIGH
) -> List[Path]:
    """
    Runs scene detection on input_file with given threshold,
    extracts each detected scene as separate clip files in output_dir,
    named {prefix}_scene_01.mov, {prefix}_scene_02.mov, etc.

    Returns list of extracted scene file paths.
    """
    verbose_log(f"Starting scene split on {input_file} with threshold {threshold}")
    duration = get_video_duration(input_file)
    scene_timestamps = detect_scene_changes(input_file, threshold)
    segments = build_scene_segments(scene_timestamps, duration)
    verbose_log(f"Extracting {len(segments)} segments from {input_file}")
    output_files = extract_segments(input_file, segments, output_dir, prefix)
    verbose_log(f"Finished extracting segments for {input_file}")
    return output_files