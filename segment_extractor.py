import subprocess
from pathlib import Path
from typing import List, Tuple
from utils import verbose_log

def extract_segments(
    input_file: Path,
    segments: List[Tuple[float, float]],
    output_dir: Path,
    prefix: str = "clip"
) -> List[Path]:
    """
    Extracts multiple segments from input_file defined by (start_sec, end_sec).

    Saves each segment as a separate file in output_dir with names:
        {prefix}_01.mov, {prefix}_02.mov, ...

    Uses ffmpeg with -ss and -to and stream copy (-c copy) for lossless extraction.

    Returns a list of Paths to the extracted segment files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    verbose_log(f"Starting extraction of {len(segments)} segments from {input_file}")
    output_files = []

    for i, (start, end) in enumerate(segments, start=1):
        duration = end - start
        output_path = output_dir / f"{prefix}_{i:02d}.mov"
        cmd = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",
            "-ss", str(start),
            "-i", str(input_file),
            "-t", str(duration),
            "-c", "copy",
            str(output_path)
        ]
        verbose_log(f"Extracting segment {i}: {start:.2f} to {end:.2f} → {output_path.name}")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed to extract segment {i} ({start}-{end})")
        output_files.append(output_path)

    verbose_log(f"Completed extraction of {len(output_files)} segments")
    return output_files