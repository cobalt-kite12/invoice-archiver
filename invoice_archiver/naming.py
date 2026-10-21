"""命名规则：项目-金额-MMDD.pdf；附属单据在日期后加 -行程单 / -运单明细；
同名但发票号不同时加 -2、-3 …"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable

_BAD = re.compile(r'[\\/:*?"<>|\s]+')


def clean(s: str) -> str:
    return _BAD.sub("", s).strip(".-") or "未知项目"


def base_stem(item: str, amount: Decimal, issued: date) -> str:
    return f"{clean(item)}-{amount:.2f}-{issued:%m%d}"


def unique_stem(stem: str, taken: Callable[[str], bool]) -> str:
    """taken(stem) 为 True 表示该名字已被另一张发票占用。"""
    if not taken(stem):
        return stem
    n = 2
    while taken(f"{stem}-{n}"):
        n += 1
    return f"{stem}-{n}"


def companion_name(invoice_stem: str, kind: str) -> str:
    return f"{invoice_stem}-{kind}.pdf"


def period_of(issued: date, cycle_start_day: int = 1) -> str:
    """归档月份 YYYY-MM。cycle_start_day=1 为自然月；
    例如 21 表示每月 21 日至次月 20 日归入次月。"""
    y, m = issued.year, issued.month
    if cycle_start_day > 1 and issued.day >= cycle_start_day:
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return f"{y:04d}-{m:02d}"


def safe_filename(name: str) -> str:
    return Path(clean(Path(name).stem) + Path(name).suffix.lower()).name
