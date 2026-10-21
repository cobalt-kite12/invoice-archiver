"""命令行入口：python -m invoice_archiver <命令>。成功时安静，失败时退出码非 0。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, nuonuo
from .archiver import Archiver
from .config import Config, load_config
from .parse import parse_pdf
from .sources import iter_eml, iter_imap


def _run(cfg: Config, sources, dry_run: bool, verbose: bool) -> int:
    arch = Archiver(cfg, dry_run=dry_run)
    failed = 0
    for name, raw in sources:
        res = arch.process_raw(raw)
        if res.failures:
            failed += 1
            for f in res.failures:
                print(f"[失败] {name}: {f}", file=sys.stderr)
        if verbose:
            for p in res.filed:
                print(f"[归档] {p}")
            for no in res.duplicates:
                print(f"[重复] 发票号尾号 {no[-4:]} 已归档过，跳过")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="invoice-archiver", description="邮件发票自动归档")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="按配置处理邮件来源（eml 目录或 IMAP）")
    r.add_argument("-c", "--config", required=True)
    r.add_argument("--dry-run", action="store_true", help="只解析不写文件")
    r.add_argument("-v", "--verbose", action="store_true")

    e = sub.add_parser("eml", help="处理指定的 .eml 文件或目录")
    e.add_argument("paths", nargs="+", type=Path)
    e.add_argument("-c", "--config", required=True)
    e.add_argument("--dry-run", action="store_true")
    e.add_argument("-v", "--verbose", action="store_true")

    p = sub.add_parser("parse", help="解析一张发票 PDF 并打印字段（调试用）")
    p.add_argument("pdf", type=Path)

    n = sub.add_parser("nuonuo", help="从诺诺网短链下载发票 PDF")
    n.add_argument("url")
    n.add_argument("out", type=Path)

    a = ap.parse_args(argv)
    if a.cmd == "parse":
        d = parse_pdf(a.pdf)
        for k, v in vars(d).items():
            print(f"{k}: {v if v is not None else '待核实'}")
        return 0 if not d.missing() else 1
    if a.cmd == "nuonuo":
        a.out.write_bytes(nuonuo.fetch_pdf(a.url))
        print(f"ok {a.out}")
        return 0

    cfg = load_config(a.config)
    if a.cmd == "eml":
        return _run(cfg, iter_eml(a.paths), a.dry_run, a.verbose)
    src = iter_imap(cfg) if cfg.source_type == "imap" else iter_eml([cfg.eml_dir])
    return _run(cfg, src, a.dry_run, a.verbose)
