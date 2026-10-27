# TC-054: 검색 Show only 필터(SPEC-041). 일치·상위 노드만 표시, 일치 수 유지, 끄기·검색어 지우기 복귀, 설정 유지.
from __future__ import annotations

import tempfile
import time

from PySide6.QtCore import QCoreApplication, QModelIndex, QSettings

from dicom_factory import nested_file


def pump(app, cond, timeout=10.0) -> bool:
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return cond()


def visible_nodes(tree, model) -> list[int]:
    """Tree에 실제로 보이는 노드 번호(펼쳐진 것만 따라간다)."""
    out = []

    def walk(parent: QModelIndex):
        for r in range(model.rowCount(parent)):
            mi = model.index(r, 0, parent)
            out.append(mi.internalId())
            if tree.isExpanded(mi):
                walk(mi)

    walk(QModelIndex())
    return out


def all_nodes(model) -> int:
    def count(parent: QModelIndex) -> int:
        n = model.rowCount(parent)
        return n + sum(count(model.index(r, 0, parent)) for r in range(n))
    return count(QModelIndex())


def new_window(tmp_settings):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tmp_settings)
    QCoreApplication.setOrganizationName("Vieworks")
    QCoreApplication.setApplicationName("DicomTagExplorerTestShowOnly")
    from dicom_tag_explorer.ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    return w


def open_one(qapp, w, path):
    from dicom_tag_explorer.ui.explorer_dock import TAB_FILES
    w.open_paths([path], add_recent=False)
    assert pump(qapp, lambda: w.batch is not None and w.batch.finished)
    f = next(iter(w.files.values()))
    w.dock.select_key(f.key, TAB_FILES, emit=True)
    assert pump(qapp, lambda: w.cur_file is f and w.tag.model.file is f)
    return f


def search(qapp, w, text):
    w.tag.search_edit.setText(text)
    assert pump(qapp, lambda: not w.tag.debounce.isActive() and w.tag.count_label.text() not in ("", "Searching…")
                or (text == "" and not w.tag.debounce.isActive()))
    pump(qapp, lambda: False, 0.1)


def test_tc054_show_only(qapp, tmp_path):
    settings_dir = tempfile.mkdtemp()
    w = new_window(settings_dir)
    try:
        assert not w.tag.show_only_chk.isChecked()  # 기본은 꺼짐
        f = open_one(qapp, w, nested_file(tmp_path / "n.dcm"))
        model, tree = w.tag.model, w.tag.tree
        total = all_nodes(model)
        search(qapp, w, "CodeValue")
        matches = list(w.matches)
        assert len(matches) == 2
        count_off = w.tag.count_label.text()
        assert count_off.endswith("/ 2")
        assert all_nodes(model) == total  # 꺼져 있으면 전체 목록 + 하이라이트

        w.tag.show_only_chk.setChecked(True)
        qapp.processEvents()
        ancestors = {a for m in matches for a in f.index.depth_path(m)[:-1]}
        shown = visible_nodes(tree, model)
        assert set(shown) == set(matches) | ancestors  # 일치 노드와 상위 노드만, 상위는 펼쳐짐
        assert all_nodes(model) == len(shown)
        assert w.tag.count_label.text() == count_off  # 일치 수는 같다 (상위 노드는 세지 않는다)
        assert all(a not in model.matches for a in ancestors)  # 상위 노드는 하이라이트하지 않는다
        sel = w.tag.current_node()
        assert sel in matches
        w.search_step(1)  # F3 이동은 두 모드에서 같다
        assert w.tag.current_node() in matches and w.tag.count_label.text() == "2 / 2"
        sel = w.tag.current_node()

        search(qapp, w, "no such text anywhere")
        assert all_nodes(model) == 0  # 0건이면 Tree가 빈다
        assert w.tag.count_label.text() == "0 / 0"
        search(qapp, w, "")
        assert all_nodes(model) == total  # 검색어를 지우면 켜진 상태에서도 전체 목록

        search(qapp, w, "CodeValue")
        w.search_step(1)
        sel = w.tag.current_node()
        w.tag.show_only_chk.setChecked(False)
        qapp.processEvents()
        assert all_nodes(model) == total  # 끄면 전체 행 수로 돌아온다
        assert w.tag.current_node() == sel  # 선택 유지
        w.tag.show_only_chk.setChecked(True)
        qapp.processEvents()
    finally:
        w.close()
    w2 = new_window(settings_dir)
    try:
        assert w2.tag.show_only_chk.isChecked()  # 설정값이 다음 실행에 유지된다
    finally:
        w2.close()


def test_hidden_node_from_raw_keeps_selection(qapp, tmp_path):
    w = new_window(tempfile.mkdtemp())
    try:
        f = open_one(qapp, w, nested_file(tmp_path / "n.dcm"))
        w.tag.show_only_chk.setChecked(True)
        search(qapp, w, "CodeValue")
        sel = w.tag.current_node()
        hidden = f.index.find_child(-1, 0x00100010)  # PatientName: 일치도 상위도 아니다
        assert not w.tag.model.is_visible(hidden)
        w.raw.hex.cursorMoved.emit(f.index.start[hidden])
        qapp.processEvents()
        assert w.tag.current_node() == sel
        assert w.statusBar().currentMessage() != "" and "0x" not in w.statusBar().currentMessage()
        assert w.tag.show_only_chk.isEnabled()
    finally:
        w.close()
