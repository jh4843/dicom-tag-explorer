# 사용자 데이터 폴더 테스트: 로그는 DicomTagExplorer\logs, 설정은 DicomTagExplorer\settings.ini에 둔다.
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from dicom_tag_explorer import appdata


def test_log_dir_under_app_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    d = appdata.log_dir()
    assert d == tmp_path / "DicomTagExplorer" / "logs" and d.is_dir()


def test_settings_file_in_app_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    appdata.init_settings_path()
    try:
        s = appdata.app_settings()
        s.setValue("ui/theme", "light")
        s.sync()
        assert Path(s.fileName()) == tmp_path / "DicomTagExplorer" / "settings.ini"
        assert appdata.app_settings().value("ui/theme") == "light"
    finally:
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "unused"))
