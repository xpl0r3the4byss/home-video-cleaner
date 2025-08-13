import subprocess
from pathlib import Path
from typing import List, Tuple
from config import BLUE_R_RANGE, BLUE_G_RANGE, BLUE_B_RANGE, BLUE_TOLERANCE, FRAME_RATE_DEFAULT
from utils import verbose_log

def run_ffmpeg_get_frame_colors(input_file: Path, frame_rate: float) -> List[Tuple[int,int,int]]:
    """
    Uses ffmpeg to downscale video to 1x1 pixel per frame, extracts raw RGB bytes,
    and returns a list of (R, G, B) tuples per frame.
    """
    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-i", str(input_file),
        "-vf", "scale=1:1,format=rgb24",
        "-f", "rawvideo",
        "-"
    ]
    verbose_log(f"Running FFmpeg command to extract frame colors:\n{' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    frame_colors = []
    frame_size = 3  # RGB bytes per frame
    verbose_log("Reading frame colors...")
    frame_index = 0
    while True:
        raw = proc.stdout.read(frame_size)
        if len(raw) < frame_size:
            break
        r, g, b = raw[0], raw[1], raw[2]
        frame_colors.append((r, g, b))
        frame_index += 1
        if frame_index % int(frame_rate) == 0:
            timestamp = frame_index / frame_rate
            mins, secs = divmod(int(timestamp), 60)
            verbose_log(f"Reading frame colors... Frame {frame_index} ({mins:02d}:{secs:02d})")
    proc.wait()
    verbose_log(f"Finished reading {len(frame_colors)} frames")
    return frame_colors

def is_blue_pixel(rgb: Tuple[int,int,int], r_range, g_range, b_range) -> bool:
    """
    Returns True if the RGB pixel falls within the given tolerance ranges.
    """
    r, g, b = rgb
    return (r_range[0] <= r <= r_range[1] and
            g_range[0] <= g <= g_range[1] and
            b_range[0] <= b <= b_range[1])

def detect_non_blue_segments(
    input_file: Path,
) -> List[Tuple[float, float]]:
    """
    Detects continuous non-blue segments in the video.

    Returns list of (start_time_sec, end_time_sec) tuples representing non-blue parts.
    """
    verbose_log(f"Starting non-blue segment detection on file: {input_file}")
    frame_colors = run_ffmpeg_get_frame_colors(input_file, FRAME_RATE_DEFAULT)

    # Expand color range by tolerance
    r_range = (BLUE_R_RANGE[0]-BLUE_TOLERANCE, BLUE_R_RANGE[1]+BLUE_TOLERANCE)
    g_range = (BLUE_G_RANGE[0]-BLUE_TOLERANCE, BLUE_G_RANGE[1]+BLUE_TOLERANCE)
    b_range = (BLUE_B_RANGE[0]-BLUE_TOLERANCE, BLUE_B_RANGE[1]+BLUE_TOLERANCE)
    verbose_log(f"Using RGB blue detection ranges (with tolerance): R={r_range}, G={g_range}, B={b_range}")

    segments = []
    in_segment = False
    segment_start = 0

    for i, rgb in enumerate(frame_colors):
        if not is_blue_pixel(rgb, r_range, g_range, b_range):
            if not in_segment:
                # Start of a new non-blue segment
                in_segment = True
                segment_start = i
        else:
            if in_segment:
                # End of non-blue segment
                in_segment = False
                start_sec = segment_start / FRAME_RATE_DEFAULT
                end_sec = i / FRAME_RATE_DEFAULT
                segments.append( (start_sec, end_sec) )

    # Handle trailing segment if video ends in non-blue
    if in_segment:
        start_sec = segment_start / FRAME_RATE_DEFAULT
        end_sec = len(frame_colors) / FRAME_RATE_DEFAULT
        segments.append( (start_sec, end_sec) )

    verbose_log(f"Detected {len(segments)} non-blue segments")
    return segments