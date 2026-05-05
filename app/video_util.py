"""视频文件完整性工具。

ffmpeg segment muxer 写 MP4 时把 moov atom（索引/元信息）写在文件末尾，
等到当前段切到下一段才 close & flush。中途崩溃 / 主机重启的话 moov 缺失，
浏览器无法 seek / 播放——这种文件视为"残缺"。
"""

import os


def is_complete_mp4(path: str, tail_bytes: int = 262144) -> bool:
    """末尾若存在 'moov' atom 则视为完整。返回 False 也涵盖 OSError 路径。"""
    try:
        size = os.path.getsize(path)
        if size < 1024:
            return False
        with open(path, "rb") as f:
            f.seek(max(0, size - tail_bytes))
            tail = f.read()
        return b"moov" in tail
    except OSError:
        return False
