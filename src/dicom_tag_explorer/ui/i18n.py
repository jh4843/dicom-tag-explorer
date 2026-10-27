# 번역기 설치·교체와 언어 목록. 첫 실행 기본 언어는 영어이고, 바꾸면 LanguageChange로 재번역된다.
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QTranslator
from PySide6.QtWidgets import QApplication

from .icons import resources_dir

LANGUAGES = ("en", "ko")
DEFAULT = "en"  # 저장값이 없으면 OS 언어와 관계없이 영어 (사용자 결정, Spec 2.8.3)
LABELS = {"en": "English", "ko": "한국어"}  # 라디오 라벨은 번역하지 않는다
log = logging.getLogger("vw.i18n")
_installed: list[QTranslator] = []
_current = DEFAULT


def i18n_dir() -> Path:
    return resources_dir() / "i18n"


def qt_translations_dir() -> Path:
    if getattr(sys, "frozen", False):
        p = Path(sys._MEIPASS) / "PySide6" / "translations"
        if p.is_dir():
            return p
    return Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))


def current() -> str:
    return _current


def _load(app: QApplication, path: Path) -> bool:
    t = QTranslator(app)
    if path.is_file() and t.load(str(path)):
        app.installTranslator(t)
        _installed.append(t)
        return True
    log.warning("번역 파일을 불러오지 못했습니다: %s", path.name)
    return False


def apply(app: QApplication, lang: str) -> None:
    """이전 번역기를 모두 제거하고 새로 설치한다. Qt가 모든 위젯에 LanguageChange를 보낸다."""
    global _current
    if lang not in LANGUAGES:
        lang = DEFAULT
    for t in _installed:
        app.removeTranslator(t)
    _installed.clear()
    _current = lang
    if lang == "ko":
        _load(app, i18n_dir() / "dicom_tag_explorer_ko.qm")
        _load(app, qt_translations_dir() / "qtbase_ko.qm")
    else:
        _load(app, i18n_dir() / "dicom_tag_explorer_en.qm")
