"""Platform limits used by lk_platform_check (and warnings in lk_export_preset).

!!! VERIFY CURRENT LIMITS !!!  Platforms change these without notice. The numbers below are best-effort
defaults from public documentation at the time of writing. Edit this dict freely: every key is optional
(None / missing = "not checked").

Keys
  label                 human name
  max_duration_s / min_duration_s
  aspects               allowed aspect ratios as "W:H" strings (2 % tolerance)
  min_width / min_height / max_width / max_height   pixels
  recommended_size      [W, H] used by lk_export_preset and as a soft hint
  max_fps
  max_size_mb           decimal megabytes (1 MB = 1,000,000 bytes)
  video_codecs / audio_codecs   accepted ffprobe codec names
  loudness_lufs / loudness_tolerance / max_true_peak_db   integrated loudness target, +/- LU, dBTP ceiling
"""

PLATFORM_RULES = {
    "reels": {
        "label": "Instagram Reels", "max_duration_s": 180, "min_duration_s": 3, "aspects": ["9:16"],
        "min_width": 540, "recommended_size": [1080, 1920], "max_fps": 60, "max_size_mb": 4000,
        "video_codecs": ["h264"], "audio_codecs": ["aac"],
        "loudness_lufs": -14, "loudness_tolerance": 2, "max_true_peak_db": -1.0,
    },
    "tiktok": {
        "label": "TikTok", "max_duration_s": 600, "min_duration_s": 1, "aspects": ["9:16"],
        "min_width": 540, "recommended_size": [1080, 1920], "max_fps": 60, "max_size_mb": 287,
        "video_codecs": ["h264", "hevc"], "audio_codecs": ["aac"],
        "loudness_lufs": -14, "loudness_tolerance": 2, "max_true_peak_db": -1.0,
    },
    "shorts": {
        "label": "YouTube Shorts", "max_duration_s": 180, "min_duration_s": 1, "aspects": ["9:16", "1:1"],
        "min_width": 540, "recommended_size": [1080, 1920], "max_fps": 60, "max_size_mb": None,
        "video_codecs": ["h264", "hevc", "vp9", "av1"], "audio_codecs": ["aac", "opus"],
        "loudness_lufs": -14, "loudness_tolerance": 2, "max_true_peak_db": -1.0,
    },
    "youtube_1080p": {
        "label": "YouTube 1080p", "max_duration_s": 43200, "min_duration_s": 1, "aspects": ["16:9"],
        "min_width": 1280, "recommended_size": [1920, 1080], "max_fps": 60, "max_size_mb": None,
        "video_codecs": ["h264", "hevc", "vp9", "av1"], "audio_codecs": ["aac", "opus"],
        "loudness_lufs": -14, "loudness_tolerance": 2, "max_true_peak_db": -1.0,
    },
    "youtube_4k": {
        "label": "YouTube 4K", "max_duration_s": 43200, "min_duration_s": 1, "aspects": ["16:9"],
        "min_width": 3840, "recommended_size": [3840, 2160], "max_fps": 60, "max_size_mb": None,
        "video_codecs": ["h264", "hevc", "vp9", "av1"], "audio_codecs": ["aac", "opus"],
        "loudness_lufs": -14, "loudness_tolerance": 2, "max_true_peak_db": -1.0,
    },
    "x_twitter": {
        "label": "X (Twitter)", "max_duration_s": 140, "min_duration_s": 0.5, "aspects": ["16:9", "1:1", "9:16"],
        "max_width": 1920, "max_height": 1920, "recommended_size": [1280, 720], "max_fps": 60, "max_size_mb": 512,
        "video_codecs": ["h264"], "audio_codecs": ["aac"],
        "loudness_lufs": None, "loudness_tolerance": None, "max_true_peak_db": None,
    },
    "discord_8mb": {
        "label": "Discord (8 MB upload)", "max_duration_s": None, "min_duration_s": None, "aspects": None,
        "recommended_size": [1280, 720], "max_fps": 60, "max_size_mb": 8,
        "video_codecs": ["h264"], "audio_codecs": ["aac"],
        "loudness_lufs": None, "loudness_tolerance": None, "max_true_peak_db": None,
    },
    "web_mp4": {
        "label": "Generic web MP4 (H.264 + AAC)", "max_duration_s": None, "min_duration_s": None, "aspects": None,
        "recommended_size": None, "max_fps": 60, "max_size_mb": None,
        "video_codecs": ["h264"], "audio_codecs": ["aac"],
        "loudness_lufs": None, "loudness_tolerance": None, "max_true_peak_db": None,
    },
}
