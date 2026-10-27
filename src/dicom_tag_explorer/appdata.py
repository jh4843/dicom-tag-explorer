# 사용자 데이터 폴더(%LOCALAPPDATA%\DicomTagExplorer)의 로그 폴더와 설정 파일(settings.ini) 위치를 정한다.
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings

APP_DIR = "DicomTagExplorer"


def base_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or str(Path.home()))


def log_dir() -> Path:
    d = base_dir() / APP_DIR / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def init_settings_path() -> None:
    """설정 파일을 레지스트리 대신 <base>\\DicomTagExplorer\\settings.ini에 둔다. 테스트는 setPath를 임시 폴더로 바꾼다."""
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(base_dir()))


def app_settings() -> QSettings:
    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, APP_DIR, "settings")
