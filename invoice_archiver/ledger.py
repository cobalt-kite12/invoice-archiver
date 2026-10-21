"""CSV 台账：按发票号去重，同时记录已处理过的邮件，避免重复下载诺诺链接。"""
from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from pathlib import Path

FIELDS = ["开票日期", "项目", "金额", "销售方", "发票号", "文件名", "附带文件",
          "归档目录", "来源邮件主题", "归档时间"]


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        self.rows: list[dict[str, str]] = []
        if path.exists():
            with path.open(encoding="utf-8-sig", newline="") as f:
                self.rows = list(csv.DictReader(f))
        self.seen_path = path.with_name(path.stem + ".messages.txt")
        self.seen: set[str] = set()
        if self.seen_path.exists():
            self.seen = set(self.seen_path.read_text(encoding="utf-8").split())

    # ---- 发票 ----
    def has_invoice(self, invoice_no: str) -> bool:
        return any(r.get("发票号") == invoice_no for r in self.rows)

    def name_taken(self, folder: str, stem: str) -> bool:
        return any(r.get("归档目录") == folder and Path(r.get("文件名", "")).stem == stem
                   for r in self.rows)

    def add(self, row: dict[str, str]) -> None:
        row = {k: row.get(k, "") for k in FIELDS}
        row["归档时间"] = row["归档时间"] or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.rows.append(row)
        new = not self.path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if new:
                w.writeheader()
            w.writerow(row)

    # ---- 邮件 ----
    @staticmethod
    def message_key(message_id: str, fallback: bytes) -> str:
        raw = message_id.strip().encode() if message_id.strip() else fallback
        return hashlib.sha256(raw).hexdigest()[:32]

    def message_seen(self, key: str) -> bool:
        return key in self.seen

    def mark_message(self, key: str) -> None:
        if key in self.seen:
            return
        self.seen.add(key)
        self.seen_path.parent.mkdir(parents=True, exist_ok=True)
        with self.seen_path.open("a", encoding="utf-8") as f:
            f.write(key + "\n")
