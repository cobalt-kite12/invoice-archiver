"""邮件来源：本地 .eml 目录，或 IMAP 邮箱（只读方式打开，不改邮件状态）。"""
from __future__ import annotations

import imaplib
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator

from .config import Config


def iter_eml(paths: list[Path]) -> Iterator[tuple[str, bytes]]:
    for p in paths:
        if p.is_dir():
            for f in sorted(p.glob("*.eml")):
                yield str(f), f.read_bytes()
        else:
            yield str(p), p.read_bytes()


def iter_imap(cfg: Config) -> Iterator[tuple[str, bytes]]:
    c = cfg.imap
    password = os.environ.get(c.password_env)
    if not (c.host and c.username and password):
        raise RuntimeError(f"IMAP 配置不完整：需要 imap.host、imap.username 和环境变量 {c.password_env}")
    since = (date.today() - timedelta(days=c.since_days)).strftime("%d-%b-%Y")
    with imaplib.IMAP4_SSL(c.host, c.port) as m:
        m.login(c.username, password)
        typ, _ = m.select(c.folder, readonly=True)
        if typ != "OK":
            raise RuntimeError(f"打不开邮箱文件夹 {c.folder}")
        typ, data = m.uid("search", None, "SINCE", since)
        for uid in (data[0] or b"").split():
            typ, msg = m.uid("fetch", uid, "(BODY.PEEK[])")
            if typ == "OK" and msg and isinstance(msg[0], tuple):
                yield f"imap:{uid.decode()}", msg[0][1]
