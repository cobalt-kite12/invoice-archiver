"""用 pdftotext 读取电子发票 PDF 的关键字段。

只依赖 poppler-utils 的 `pdftotext` 命令。解析是尽力而为：
读不出的字段为 None，由上层决定是否算失败。
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

INVOICE = "发票"
TRIP = "行程单"        # 滴滴等网约车的行程报销单
WAYBILL = "运单明细"    # 顺丰等快递的运单明细

_CJK = r"\u4e00-\u9fff"


@dataclass
class ParsedDoc:
    kind: str                     # 发票 / 行程单 / 运单明细 / 未知
    invoice_no: str | None = None
    issue_date: date | None = None
    item: str | None = None
    amount: Decimal | None = None
    seller: str | None = None

    def missing(self) -> list[str]:
        if self.kind != INVOICE:
            return []
        need = {"发票号码": self.invoice_no, "开票日期": self.issue_date,
                "项目": self.item, "金额": self.amount}
        return [k for k, v in need.items() if not v]


def pdf_to_text(path: Path) -> str:
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("找不到 pdftotext，请安装 poppler-utils")
    out = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(path), "-"],
                         capture_output=True, check=True, timeout=60)
    return out.stdout.decode("utf-8", "replace")


def classify(text: str, filename: str = "") -> str:
    head = filename + "\n" + text[:3000]
    if re.search(r"行程(报销)?单", head):
        return TRIP
    if re.search(r"运单(明细|清单)", head):
        return WAYBILL
    if re.search(r"发\s*票\s*号\s*码", text) or "价税合计" in text:
        return INVOICE
    return "未知"


def _invoice_no(text: str) -> str | None:
    m = re.search(r"发\s*票\s*号\s*码\s*[:：]?\s*(\d{8,20})", text)
    if m:
        return m.group(1)
    # 版式文件里标签和值可能被拆开：退而求其次找 20 位全电发票号码
    m = re.search(r"(?<!\d)(\d{20})(?!\d)", text)
    return m.group(1) if m else None


def _issue_date(text: str) -> date | None:
    pats = [
        r"开\s*票\s*日\s*期\s*[:：]?\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
        r"开\s*票\s*日\s*期\s*[:：]?\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})",
        r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
    ]
    for p in pats:
        m = re.search(p, text)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
    return None


def _money(s: str) -> Decimal | None:
    try:
        return Decimal(s.replace(",", "")).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _amount(text: str) -> Decimal | None:
    m = re.search(r"[（(]\s*小\s*写\s*[）)]\s*[¥￥]?\s*(-?[\d,]+\.\d{1,2})", text)
    if m:
        return _money(m.group(1))
    m = re.search(r"价\s*税\s*合\s*计[^\n]*?[¥￥]\s*(-?[\d,]+\.\d{1,2})", text)
    if m:
        return _money(m.group(1))
    vals = [_money(v) for v in re.findall(r"[¥￥]\s*(-?[\d,]+\.\d{1,2})", text)]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def _item(text: str) -> str | None:
    """取第一条「*分类*名称」，去掉分类前缀；处理名称被折到下一行的情况。"""
    chars = rf"{_CJK}A-Za-z0-9（）()·\-\u2160-\u217f"
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.search(rf"\*[^*\s]+\*\s*([{chars}]+)", line)
        if not m:
            continue
        name = m.group(1)
        col = m.start(1)
        # 折行的剩余部分：要么单独占一行（真实电子发票常顶格），要么在下一行相同列附近
        for nxt in lines[i + 1:i + 3]:
            if not nxt.strip() or "*" in nxt:
                break
            toks = nxt.split()
            if len(toks) == 1 and re.fullmatch(rf"[{chars}]{{1,8}}", toks[0]):
                name += toks[0]
                break
            frag = nxt[max(0, col - 2):col + len(name) + 4].strip()
            first = frag.split()[0] if frag.split() else ""
            if first and re.fullmatch(rf"[{_CJK}]{{1,6}}", first):
                name += first
            break
        return name
    return None


def _seller(text: str) -> str | None:
    # 全电发票里购买方、销售方的「名称：」常在同一行，销售方在右侧
    for line in text.splitlines():
        names = re.findall(r"名\s*称\s*[:：]\s*(\S+)", line)
        if len(names) >= 2:
            return names[-1]
    m = re.search(r"销\s*售\s*方[^\n]*?名\s*称\s*[:：]\s*(\S+)", text)
    return m.group(1) if m else None


def parse_text(text: str, filename: str = "", aliases: dict[str, str] | None = None) -> ParsedDoc:
    kind = classify(text, filename)
    doc = ParsedDoc(kind=kind)
    doc.invoice_no = _invoice_no(text)
    doc.issue_date = _issue_date(text)
    doc.amount = _amount(text)
    if kind == INVOICE:
        doc.item = _item(text)
        doc.seller = _seller(text)
        if doc.item and aliases:
            doc.item = aliases.get(doc.item, doc.item)
    return doc


def parse_pdf(path: Path, aliases: dict[str, str] | None = None) -> ParsedDoc:
    return parse_text(pdf_to_text(path), path.name, aliases)
