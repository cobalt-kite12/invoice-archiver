"""读取 TOML 配置（Python 3.11+ 自带 tomllib）。"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ArchiveConfig:
    output_dir: Path = Path("~/InvoiceArchive")
    ledger: str = "ledger.csv"
    cycle_start_day: int = 1
    mirror_dirs: list[Path] = field(default_factory=list)
    failed_dir: str = "_failed"


@dataclass
class ImapConfig:
    host: str = ""
    port: int = 993
    username: str = ""
    password_env: str = "INVOICE_IMAP_PASSWORD"
    folder: str = "INBOX"
    since_days: int = 30


@dataclass
class NuonuoConfig:
    enabled: bool = True
    timeout: int = 30
    retries: int = 5


@dataclass
class Config:
    archive: ArchiveConfig = field(default_factory=ArchiveConfig)
    source_type: str = "eml"
    eml_dir: Path = Path("./inbox")
    imap: ImapConfig = field(default_factory=ImapConfig)
    nuonuo: NuonuoConfig = field(default_factory=NuonuoConfig)
    item_aliases: dict[str, str] = field(default_factory=dict)

    @property
    def ledger_path(self) -> Path:
        return self.archive.output_dir / self.archive.ledger

    @property
    def failed_path(self) -> Path:
        return self.archive.output_dir / self.archive.failed_dir


def _p(value: str, base: Path) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(value)))
    return path if path.is_absolute() else (base / path)


def load_config(path: str | Path) -> Config:
    path = Path(path)
    base = path.resolve().parent
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = Config()

    a = data.get("archive", {})
    cfg.archive = ArchiveConfig(
        output_dir=_p(a.get("output_dir", "~/InvoiceArchive"), base),
        ledger=a.get("ledger", "ledger.csv"),
        cycle_start_day=int(a.get("cycle_start_day", 1)),
        mirror_dirs=[_p(d, base) for d in a.get("mirror_dirs", [])],
        failed_dir=a.get("failed_dir", "_failed"),
    )
    if not 1 <= cfg.archive.cycle_start_day <= 28:
        raise ValueError("archive.cycle_start_day 必须在 1..28 之间")

    s = data.get("source", {})
    cfg.source_type = s.get("type", "eml")
    cfg.eml_dir = _p(s.get("eml_dir", "./inbox"), base)
    if cfg.source_type not in ("eml", "imap"):
        raise ValueError("source.type 只能是 eml 或 imap")

    i = data.get("imap", {})
    cfg.imap = ImapConfig(
        host=i.get("host", ""),
        port=int(i.get("port", 993)),
        username=i.get("username", ""),
        password_env=i.get("password_env", "INVOICE_IMAP_PASSWORD"),
        folder=i.get("folder", "INBOX"),
        since_days=int(i.get("since_days", 30)),
    )
    if "password" in i:
        raise ValueError("不要把密码写进配置文件；请用 imap.password_env 指定环境变量名")

    n = data.get("nuonuo", {})
    cfg.nuonuo = NuonuoConfig(
        enabled=bool(n.get("enabled", True)),
        timeout=int(n.get("timeout", 30)),
        retries=int(n.get("retries", 5)),
    )
    cfg.item_aliases = dict(data.get("item_aliases", {}))
    return cfg
