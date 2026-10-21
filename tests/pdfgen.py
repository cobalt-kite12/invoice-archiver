"""生成合成测试 PDF（纯标准库）。

文字用 Identity-H 编码、CID = Unicode 码位，再配一个恒等 ToUnicode 映射，
所以不嵌字体也能被 pdftotext 正确读出中文。内容全部是虚构的。
"""
from __future__ import annotations


def make_pdf(lines: list[tuple[float, float, str]]) -> bytes:
    """lines: (x, y, 文本)，坐标单位 pt，A4 横向 842x595。"""
    ops = ["BT", "/F1 10 Tf"]
    for x, y, text in lines:
        hexs = "".join(f"{ord(ch):04X}" for ch in text)
        ops.append(f"1 0 0 1 {x} {y} Tm <{hexs}> Tj")
    ops.append("ET")
    content = "\n".join(ops).encode()
    cmap = (b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
            b"/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
            b"/CMapName /Adobe-Identity-UCS def /CMapType 2 def\n"
            b"1 begincodespacerange <0000> <FFFF> endcodespacerange\n"
            b"1 beginbfrange <0000> <FFFF> <0000> endbfrange\n"
            b"endcmap CMapName currentdict /CMap defineresource pop end end")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type0 /BaseFont /SynthCJK /Encoding /Identity-H "
        b"/DescendantFonts [6 0 R] /ToUnicode 7 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /SynthCJK "
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        b"/FontDescriptor 8 0 R /DW 1000 >>",
        b"<< /Length %d >>\nstream\n" % len(cmap) + cmap + b"\nendstream",
        b"<< /Type /FontDescriptor /FontName /SynthCJK /Flags 4 "
        b"/FontBBox [0 -200 1000 900] /ItalicAngle 0 /Ascent 900 /Descent -200 "
        b"/CapHeight 700 /StemV 80 >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def invoice_pdf(no: str, y: int, m: int, d: int, category: str, item: str,
                total: str, wrap: str = "", seller: str = "示例服务有限公司") -> bytes:
    """一张虚构的全电发票。wrap 非空时模拟项目名称折到下一行。"""
    lines = [
        (330, 560, "电子发票（普通发票）"),
        (600, 560, f"发票号码：{no}"),
        (600, 545, f"开票日期：{y}年{m:02d}月{d:02d}日"),
        (40, 510, "购买方信息  名称：个人"),
        (430, 510, f"销售方信息  名称：{seller}"),
        (40, 470, "项目名称"), (250, 470, "金额"), (400, 470, "税率"), (520, 470, "税额"),
        (40, 455, f"*{category}*{item}"), (250, 455, total), (400, 455, "免税"), (520, 455, "***"),
    ]
    if wrap:
        lines.append((40 + 10 * (len(category) + 2), 441, wrap))
    lines += [
        (40, 400, "合计"), (250, 400, f"¥{total}"),
        (40, 380, "价税合计（大写）"), (430, 380, f"（小写）¥{total}"),
        (40, 340, "开票人：测试"),
    ]
    return make_pdf(lines)


def companion_pdf(title: str, total: str) -> bytes:
    return make_pdf([(300, 560, title), (40, 520, "共 1 笔"), (40, 500, f"合计 {total} 元")])
