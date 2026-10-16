"""只读取文件头/尾；不猜测密钥、加密算法、正文或身份。"""

import hashlib
import os
import stat
import struct
from pathlib import Path

from ..base import UnsupportedWeChatSource


def checked_path(value):
    raw = str(value)
    path = Path(raw).expanduser()
    if not raw or "://" in raw or raw.startswith(("\\\\", "//")) or any(ord(c) < 32 for c in raw) or ".." in path.parts:
        raise UnsupportedWeChatSource("备份检查只接受明确的本机路径，不接受网络路径、URI 或路径穿越")
    # resolve 之前检查链接，包括 Windows junction/reparse point。
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise UnsupportedWeChatSource("备份检查不接受符号链接或目录联接")
    if not path.exists():
        raise UnsupportedWeChatSource("备份来源路径不存在")
    return path.resolve()


def children(path):
    entries = sorted(path.iterdir(), key=lambda p: p.name)
    if len(entries) > 20000:
        raise UnsupportedWeChatSource("单个备份目录超过结构检查上限，拒绝不受限扫描")
    for entry in entries:
        info = entry.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise UnsupportedWeChatSource("备份内含符号链接或目录联接，未继续读取")
    return entries


def file_stamp(path):
    info = path.stat()
    return info.st_size, info.st_mtime_ns, info.st_ino


def read_edges(path):
    checked_path(path)
    before = file_stamp(path)
    if not path.is_file():
        raise UnsupportedWeChatSource("备份结构需要普通文件")
    # O_RDONLY，不打开源数据库，不写入原备份。
    with path.open("rb") as handle:
        head = handle.read(128)
        handle.seek(max(0, before[0] - 128), os.SEEK_SET)
        tail = handle.read(128)
        opened = os.fstat(handle.fileno())
    if before != file_stamp(path) or (opened.st_size, opened.st_mtime_ns, opened.st_ino) != before:
        raise UnsupportedWeChatSource("备份文件在读取期间变化，请等微信备份结束后重试")
    return head, tail, before


def read_envelope(path):
    head, tail, stamp = read_edges(path)
    if len(head) < 16 or head[:4] != b"RMFH":
        raise UnsupportedWeChatSource("文件不是已识别的 RMFH 容器")
    _, session, count, flags, reserved = struct.unpack("<4sIHHI", head[:16])
    # 仅验证本次观测到的外壳投影，不据此声称完整格式/算法兼容。
    if count != 1 or reserved != 0 or flags & 0xff != 1:
        raise UnsupportedWeChatSource("RMFH 文件头不符合已观测的外壳结构，未知版本拒绝")
    if stamp[0] < 256 or len(head) != 128 or len(tail) != 128 or tail[:4] != b"RMFT":
        raise UnsupportedWeChatSource("RMFH 容器头尾不完整或布局未知，需要 128 字节头和 RMFT 尾")
    return {"layout":"rmfh-128-envelope-observed", "bytes":stamp[0], "payload_offset":128,
            "payload_bytes":stamp[0]-256, "header_count":count, "header_flags":flags,
            "header_session":session, "edge_sha256":hashlib.sha256(head+tail).hexdigest()}
