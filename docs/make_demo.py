"""生成 README 里的演示截图 docs/demo.png。

全部数据都是虚构的：用 tests/pdfgen.py 现场合成发票 PDF、打包成 .eml，
在临时目录里真实运行一次 `python -m invoice_archiver eml ... -v`，
再把命令输出和归档目录树画成一张终端风格的 PNG。

运行：python3 docs/make_demo.py   （需要 Pillow、pdftotext 和一个中文等宽字体）
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.helpers import make_eml  # noqa: E402
from tests.pdfgen import companion_pdf, invoice_pdf  # noqa: E402

# (字体文件, ttc 内序号)；Noto Sans CJK 的第 7 个是 Noto Sans Mono CJK SC
FONT_CANDIDATES = [
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 7),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 7),
    ("/System/Library/Fonts/PingFang.ttc", 0),
]


def build_inbox(inbox: Path) -> None:
    park1 = invoice_pdf("00000000000000000101", 2026, 10, 21, "生产生活服务", "停车费", "1.50",
                        seller="示例停车场有限公司")
    park2 = invoice_pdf("00000000000000000102", 2026, 10, 21, "生产生活服务", "停车费", "1.50",
                        seller="示例停车场有限公司")
    taxi = invoice_pdf("00000000000000000103", 2026, 10, 3, "交通运输服务", "客运服务", "23.00",
                       wrap="费", seller="示例出行科技有限公司")
    express = invoice_pdf("00000000000000000104", 2026, 10, 9, "物流辅助服务", "收派服务费", "8.00",
                          seller="示例速运有限公司")
    fuel = invoice_pdf("00000000000000000105", 2026, 10, 14, "汽油", "92号车用汽油", "200.00",
                       seller="示例加油站有限公司")
    mails = [
        ("01-停车.eml", make_eml("停车发票", [("发票.pdf", park1), ("发票.ofd", b"OFD")],
                                 msgid="<demo-1@example.com>")),
        ("02-停车.eml", make_eml("停车发票", [("发票.pdf", park2)], msgid="<demo-2@example.com>")),
        ("03-打车.eml", make_eml("行程发票", [("电子发票.pdf", taxi),
                                             ("行程报销单.pdf", companion_pdf("行程单", "23.00"))],
                                 msgid="<demo-3@example.com>")),
        ("04-快递.eml", make_eml("快递发票", [("电子发票.pdf", express), ("发票.xml", b"<x/>"),
                                             ("运单明细.pdf", companion_pdf("发票运单明细", "8.00"))],
                                 msgid="<demo-4@example.com>")),
        ("05-加油.eml", make_eml("加油发票", [("发票.pdf", fuel)], msgid="<demo-5@example.com>")),
        ("06-转发.eml", make_eml("Fw: 停车发票", [("发票.pdf", park1)], msgid="<demo-6@example.com>")),
    ]
    inbox.mkdir()
    for name, raw in mails:
        (inbox / name).write_bytes(raw)


def tree(folder: Path) -> list[str]:
    out = ["archive/"]
    entries = sorted(p for p in folder.iterdir() if p.name != "_failed")
    for i, p in enumerate(entries):
        last = i == len(entries) - 1
        out.append(("└── " if last else "├── ") + p.name + ("/" if p.is_dir() else ""))
        if p.is_dir():
            kids = sorted(p.iterdir())
            for j, k in enumerate(kids):
                out.append(("    " if last else "│   ") + ("└── " if j == len(kids) - 1 else "├── ") + k.name)
    return out


def run_demo() -> list[str]:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        build_inbox(tmp / "inbox")
        (tmp / "config.toml").write_text(
            '[archive]\noutput_dir = "./archive"\n[source]\ntype = "eml"\neml_dir = "./inbox"\n',
            encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        cmd = [sys.executable, "-m", "invoice_archiver", "eml", "inbox", "-c", "config.toml", "-v"]
        res = subprocess.run(cmd, cwd=tmp, env=env, capture_output=True, text=True)
        if res.returncode != 0:
            raise SystemExit(f"demo run failed:\n{res.stdout}\n{res.stderr}")
        output = (res.stdout + res.stderr).replace(str(tmp.resolve()) + os.sep, "").replace(str(tmp) + os.sep, "")
        lines = ["$ python -m invoice_archiver eml inbox/ -c config.toml -v"]
        lines += [ln for ln in output.splitlines() if ln.strip()]
        lines += ["", "$ tree archive"] + tree(tmp / "archive")
        return lines


def render(lines: list[str], out: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    found = next(((f, i) for f, i in FONT_CANDIDATES if Path(f).exists()), None)
    if not found:
        raise SystemExit("找不到中文字体，请修改 FONT_CANDIDATES")
    font = ImageFont.truetype(found[0], 22, index=found[1])
    pad, lh, bar = 28, 34, 44
    width = max(int(font.getlength(ln)) for ln in lines) + pad * 2
    width = max(width, 900)
    height = bar + pad + lh * len(lines) + pad
    img = Image.new("RGB", (width, height), (30, 32, 40))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width, bar], fill=(48, 50, 60))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([18 + i * 26, 15, 32 + i * 26, 29], fill=c)
    d.text((width // 2, bar // 2), "invoice-archiver demo (synthetic data)", font=font,
           fill=(170, 170, 180), anchor="mm")
    y = bar + pad
    for ln in lines:
        color = (220, 220, 225)
        if ln.startswith("$"):
            color = (120, 200, 255)
        elif ln.startswith("[归档]"):
            color = (140, 220, 140)
        elif ln.startswith("[重复]"):
            color = (240, 200, 110)
        elif ln.startswith("[失败]"):
            color = (255, 120, 120)
        d.text((pad, y), ln, font=font, fill=color)
        y += lh
    img.save(out, "PNG", optimize=True)  # Pillow 不写 EXIF / 文本元数据


if __name__ == "__main__":
    lines = run_demo()
    print("\n".join(lines))
    render(lines, ROOT / "docs" / "demo.png")
    print("saved docs/demo.png")
