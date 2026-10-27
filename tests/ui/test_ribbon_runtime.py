# 리본 런타임 회귀 테스트: 테마·언어 전환 후 큰 버튼 두 줄 라벨 유지(R-01), 폭에 따른 축소 순서와 명령 접근(R-02).
from __future__ import annotations

import shutil
import tempfile

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt
from PySide6.QtWidgets import QToolButton, QWidget

import i18n as i18n_tool
from dicom_tag_explorer.ui import i18n, theme
from dicom_tag_explorer.ui.actions import COMMANDS, RIBBON_LAYOUT, ActionRegistry
from dicom_tag_explorer.ui.ribbon import LARGE_W, MODES, LargeButton, Ribbon, two_lines

LEVEL = {m: k for k, m in enumerate(MODES)}


def pump(app, n=5):
    for _ in range(n):
        app.processEvents()


@pytest.fixture
def qm_dir(tmp_path, monkeypatch):
    """커밋된 .ts로 임시 폴더에 .qm을 만들고 번역기가 그것을 읽게 한다."""
    for name in (i18n_tool.KO, i18n_tool.EN):
        shutil.copy(i18n_tool.I18N / name, tmp_path / name)
    assert i18n_tool.release(tmp_path) == 0
    monkeypatch.setattr(i18n, "i18n_dir", lambda: tmp_path)
    return tmp_path


def _large_labels(ribbon) -> list[tuple[str, str]]:
    """(라벨, 액션 텍스트) — 현재 리본 본문의 큰 버튼."""
    out = []
    for b in ribbon.body.findChildren(LargeButton):
        a = b.action_() if b.large else None
        if a is not None:
            out.append((b.text(), a.text().replace("&", "")))
    return out


def _assert_two_lines(ribbon, where: str) -> None:
    labels = _large_labels(ribbon)
    assert labels, where
    multi = 0
    for text, plain in labels:
        expected = two_lines(plain, theme.font("caption"), LARGE_W - 4)
        assert text == expected, (where, text, expected)
        if "\n" in expected:
            multi += 1
            assert "\n" in text, (where, text)
    assert multi > 0, (where, labels)


def test_r01_labels_survive_theme_and_language_switch(qapp, qm_dir):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())
    QCoreApplication.setOrganizationName("Vieworks")
    QCoreApplication.setApplicationName("DicomTagExplorerTestR01")
    theme.apply(qapp, "dark")
    i18n.apply(qapp, "en")
    from dicom_tag_explorer.ui.main_window import MainWindow
    w = MainWindow()
    w.resize(1280, 720)
    w.show()
    pump(qapp)
    try:
        for tab in range(len(RIBBON_LAYOUT)):
            w.ribbon.set_tab(tab)
            pump(qapp)
            _assert_two_lines(w.ribbon, f"dark/en tab {tab}") if tab < 3 else None
        w.ribbon.set_tab(0)
        _assert_two_lines(w.ribbon, "dark/en")
        w.set_theme("light")
        pump(qapp)
        _assert_two_lines(w.ribbon, "light/en")
        w.set_language("ko")
        pump(qapp)
        assert w.actions["file.open_folder"].text() == "폴더 열기"
        _assert_two_lines(w.ribbon, "light/ko")
        # 아이콘만 다시 설정해도(QAction.changed) 라벨이 풀리지 않는다
        w.actions.refresh_icons()
        pump(qapp)
        _assert_two_lines(w.ribbon, "light/ko after refresh_icons")
    finally:
        w.close()
        i18n.apply(qapp, "en")
        theme.apply(qapp, "dark")


# ---- R-02: 리본만 띄워 폭 줄이기 ----
def _registry(owner: QWidget) -> ActionRegistry:
    reg = ActionRegistry(owner)
    for name in COMMANDS:
        reg.define(name)
    # 영어 원문과 비슷한 길이의 텍스트 (예: file.open_folder → "Open Folder")
    reg.set_texts({n: n.split(".", 1)[1].replace("_", " ").title() for n in COMMANDS})
    return reg


def _reachable(ribbon) -> set[str]:
    names = set()
    for b in ribbon.body.findChildren(QToolButton):
        if not b.isVisible():
            continue
        # QToolButton.menu()는 부르지 않는다 (PySide6에서 소유권이 바뀌어 메뉴가 지워진다). 버튼이 보관한 dropdown을 쓴다
        a = b.action_() if isinstance(b, LargeButton) else b.defaultAction()
        m = getattr(b, "dropdown", None)
        if a is not None and a.objectName():
            if a.menu() is None or (m is not None and m.menuAction() in b.actions()):
                names.add(a.objectName())  # 드롭다운 명령은 메뉴가 실제로 붙어 있어야 접근할 수 있다
        if m is not None:
            for x in m.actions():
                names.add(x.objectName() or (x.menu().objectName() if x.menu() else ""))
    names.discard("")
    return names


def test_dropdown_button_keeps_menu(qapp):
    """setDefaultAction(menuAction) 뒤 setMenu(같은 메뉴)는 Qt가 둘 다 지운다. 드롭다운 버튼에 메뉴가 남아 있어야 한다."""
    theme.apply(qapp, "dark")
    owner = QWidget()
    reg = _registry(owner)
    reg.menu("file.recent").addAction("recent item")
    rb = Ribbon(reg)
    rb.resize(1600, rb.height())
    rb.show()
    pump(qapp)
    try:
        btn = next(b for b in rb.body.findChildren(LargeButton) if b.action_() is reg["file.recent"])
        assert btn.dropdown is reg.menu("file.recent")
        assert reg["file.recent"] in btn.actions()  # setMenu가 붙인 menuAction (Qt 수준 연결)
        assert [a.text() for a in btn.dropdown.actions()] == ["recent item"]
        assert "\n" in btn.text() or " " not in btn.text()
        reg.refresh_icons()
        pump(qapp)
        assert reg["file.recent"] in btn.actions() and not btn.icon().isNull()
    finally:
        rb.close()
        owner.deleteLater()


def test_r02_shrinks_right_to_left_and_keeps_commands_reachable(qapp):
    theme.apply(qapp, "dark")
    owner = QWidget()
    reg = _registry(owner)
    rb = Ribbon(reg)
    rb.show()
    try:
        for tab, (_, groups) in enumerate(RIBBON_LAYOUT):
            rb.set_tab(tab)
            want = {n for _, cmds in groups for n, _ in cmds}
            prev_total = -1
            seen_modes = set()
            for width in range(2000, 99, -20):  # 단계 경계를 건너뛰지 않게 촘촘히 (작은 버튼 구간은 55 px 이상, 여백이 바뀌면 경계도 움직인다)
                rb.resize(width, rb.height())
                pump(qapp)
                assert rb.width() == width, (tab, width, rb.width())  # 리본이 최소 폭을 강제하지 않는다
                modes = rb.group_modes()
                levels = [LEVEL[m] for m in modes]
                seen_modes.update(modes)
                # 오른쪽 그룹부터 줄인다: 왼쪽 그룹이 줄었으면 그 오른쪽은 모두 드롭다운이다
                for i, lv in enumerate(levels):
                    if lv > 0:
                        assert all(x == LEVEL["dropdown"] for x in levels[i + 1:]), (tab, width, modes)
                # 폭이 줄면 축소 단계는 늘기만 한다
                assert sum(levels) >= prev_total, (tab, width, modes)
                prev_total = sum(levels)
                # 모든 명령에 접근할 수 있다 (버튼 또는 드롭다운 메뉴)
                assert want <= _reachable(rb), (tab, width, modes, want - _reachable(rb))
            assert rb.group_modes()[0] == "dropdown" or len(groups) == 1 and rb.group_modes() == ["dropdown"], (
                tab, rb.group_modes())
            # 큰 버튼이 있는 그룹은 드롭다운 전에 작은 버튼 단계를 거친다
            if any(s == "L" for _, cmds in groups for _, s in cmds) and len(groups) > 1:
                assert "small" in seen_modes, (tab, seen_modes)
    finally:
        rb.close()
        owner.deleteLater()


def _flush_deferred_deletes() -> None:
    """모달 창의 중첩 이벤트 루프가 하는 것처럼 deleteLater로 미뤄 둔 삭제를 처리한다."""
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_qa02_view_tab_survives_deleted_ribbon_buttons(qapp):
    """QA-02: 보기 탭 버튼이 지워진 뒤(모달 창을 열고 닫으면 일어난다)에도 탐색 Pane 명령이 살아 있어야 한다."""
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())
    QCoreApplication.setOrganizationName("Vieworks")
    QCoreApplication.setApplicationName("DicomTagExplorerTestQA02")
    theme.apply(qapp, "dark")
    from dicom_tag_explorer.ui.main_window import MainWindow
    w = MainWindow()
    w.resize(1280, 720)
    w.show()
    pump(qapp)
    try:
        view = next(i for i, (_, groups) in enumerate(RIBBON_LAYOUT)
                    if any(n == "view.explorer" for _, cmds in groups for n, _ in cmds))
        for tab in (*range(len(RIBBON_LAYOUT)), 0):
            w.ribbon.set_tab(tab)
            pump(qapp)
        _flush_deferred_deletes()
        pump(qapp)
        assert [n for n in w.actions.names() if not shiboken6.isValid(w.actions[n])] == []
        a = w.actions["view.explorer"]
        w.ribbon.set_tab(view)  # 예전에는 여기서 RuntimeError, 본문이 비었다
        pump(qapp)
        assert any(b.action_() is a for b in w.ribbon.body.findChildren(LargeButton))
        w.actions.refresh_icons()
        # 명령과 Dock 표시 상태가 서로 맞는다
        assert a.isChecked() == w.dock.isVisible()
        a.trigger()
        pump(qapp)
        assert w.dock.isHidden() and not a.isChecked()
        a.trigger()
        pump(qapp)
        assert w.dock.isVisible() and a.isChecked()
        w.dock.close()  # Dock 자체의 닫기 버튼
        pump(qapp)
        assert not a.isChecked()
    finally:
        w.close()


def test_qa03_focus_does_not_shrink_labels(qapp):
    """QA-03: 키보드 포커스를 받아도 리본 버튼 라벨 영역이 줄지 않는다(말줄임 없음). 테두리 안쪽 그림이 포커스 전후로 같아야 한다."""
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())
    QCoreApplication.setOrganizationName("Vieworks")
    QCoreApplication.setApplicationName("DicomTagExplorerTestQA03")
    theme.apply(qapp, "dark")
    from dicom_tag_explorer.ui.main_window import MainWindow
    w = MainWindow()
    w.resize(1280, 720)
    w.show()
    w.activateWindow()
    pump(qapp)
    try:
        checked = 0
        for tab in range(len(RIBBON_LAYOUT)):
            w.ribbon.set_tab(tab)
            pump(qapp)
            for b in w.ribbon.body.findChildren(QToolButton):
                if not b.isVisible() or not b.text():
                    continue
                b.clearFocus()
                pump(qapp, 2)
                before = b.grab().toImage()
                b.setFocus(Qt.FocusReason.TabFocusReason)
                pump(qapp, 2)
                if not b.hasFocus():
                    pytest.skip("이 플랫폼에서는 창이 포커스를 받지 못한다")
                after = b.grab().toImage()
                inner = (3, 3, before.width() - 6, before.height() - 6)  # 포커스 테두리(2px)와 둥근 모서리 안티에일리어싱 안쪽
                assert after.copy(*inner) == before.copy(*inner), (tab, b.accessibleName())
                checked += 1
        assert checked > 10
    finally:
        w.close()
