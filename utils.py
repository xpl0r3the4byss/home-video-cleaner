import subprocess
from pathlib import Path

VERBOSE = True

def verbose_log(msg: str) -> None:
    """
    Print message only if VERBOSE is True.
    """
    if VERBOSE:
        print(msg)

def log(msg: str) -> None:
    """
    Always print message.
    """
    print(msg)

def run_ffmpeg_command(cmd: list) -> None:
    """
    Runs an ffmpeg command list, raises RuntimeError if it fails.
    """
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg command failed:\n{result.stderr}")

def ensure_dir(path: Path) -> None:
    """
    Ensure that a directory exists; creates if not.
    """
    path.mkdir(parents=True, exist_ok=True)

def get_file_stem(filename: str) -> str:
    """
    Returns the filename without extension.
    """
    return Path(filename).stem