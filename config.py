

# Configuration settings for home_video_cleaner

# Frame rate assumed if not detected automatically
FRAME_RATE_DEFAULT = 29.97

# RGB ranges for blue detection (inclusive)
BLUE_R_RANGE = (10, 13)
BLUE_G_RANGE = (0, 1)
BLUE_B_RANGE = (237, 239)

# Tolerance for blue detection RGB matching (+/-)
BLUE_TOLERANCE = 1

# Scene detection thresholds
SCENE_THRESHOLD_HIGH = 0.35
SCENE_THRESHOLD_LOW = 0.3

# Output directory for all processed files
OUTPUT_DIR = "output"

# Aliases for compatibility
HIGH_THRESHOLD = SCENE_THRESHOLD_HIGH
LOW_THRESHOLD = SCENE_THRESHOLD_LOW