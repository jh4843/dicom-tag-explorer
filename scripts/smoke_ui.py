# 오프스크린 Qt로 메인 창을 띄워 샘플 폴더를 열고 주요 흐름을 자동 점검하는 스모크 스크립트.
"""사용법: .venv\\Scripts\\python scripts\\smoke_ui.py [샘플 폴더]

pytest 대상이 아니다(Spec 2.1: UI는 수동 확인). G2 실행 확인을 보조한다.
환자 식별 값은 출력하지 않는다.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QCoreApplication, QPoint, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

DEFAULT = Path(r"E:\JaeHyeokDoc\#1_Pathology\03_Images\DICOM")
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"[{'OK' if ok else 'NG'}] {name} {detail}")


def wait(cond, timeout=60.0) -> bool:
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    if not root.is_dir():
        print("샘플 폴더가 없습니다:", root)
        return 2
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())
    from dicom_tag_explorer.app import tune_gil
    tune_gil()
    app = QApplication(sys.argv)
    QCoreApplication.setOrganizationName("Vieworks")
    QCoreApplication.setApplicationName("DicomTagExplorerSmoke")
    from dicom_tag_explorer.ui.explorer_dock import TAB_DICOMDIR, TAB_FILES, TAB_WSI
    from dicom_tag_explorer.ui import i18n, theme
    from dicom_tag_explorer.ui.actions import RIBBON_LAYOUT
    from dicom_tag_explorer.ui.main_window import KEY_LANGUAGE, KEY_RIBBON, KEY_THEME, MainWindow, saved_language_and_theme
    from dicom_tag_explorer.core.dicomdir import iter_records

    lang0, th0 = saved_language_and_theme(QSettings())
    check("첫 실행 기본값 영어·다크", (lang0, th0) == ("en", "dark"))
    theme.apply(app, th0)
    i18n.apply(app, lang0)
    w = MainWindow()
    w.resize(1280, 720)
    w.show()
    QApplication.processEvents()
    reg = w.actions
    from collections import Counter
    keys = [k.toString() for n in reg.names() for k in reg[n].shortcuts()]
    dup = [k for k, c in Counter(keys).items() if c > 1]
    check("레지스트리 단축키 중복 없음 (TC-049)", not dup, f"명령 {len(reg.names())}개, 단축키 {len(keys)}개 {dup}")
    check("메뉴바 없음, 리본 탭 4개", w.menuBar() is None or not w.menuBar().actions(),
          f"탭 {[b.text() for b in w.ribbon.tab_buttons]}")
    ribbon_names = [n for _, groups in RIBBON_LAYOUT for _, cmds in groups for n, _ in cmds]
    check("리본 명령이 모두 레지스트리에 있음", set(ribbon_names) <= set(reg.names()))
    check("타이틀바 캡션 버튼 46×32 ×4",
          all(b.size().width() == 46 and b.size().height() == 32 for b in
              (w.titlebar.btn_settings, w.titlebar.btn_min, w.titlebar.btn_max, w.titlebar.btn_close)))
    from PySide6.QtWidgets import QToolButton
    from dicom_tag_explorer.ui.ribbon import MODES
    rule_ok, reach_ok, detail = True, True, {}
    for k, (_, groups) in enumerate(RIBBON_LAYOUT):
        w.ribbon.set_tab(k)
        QApplication.processEvents()
        lv = [MODES.index(m) for m in w.ribbon.group_modes()]
        # 오른쪽 그룹부터 줄인다: 줄어든 그룹의 오른쪽은 모두 드롭다운이어야 한다
        rule_ok &= all(all(x == 2 for x in lv[i + 1:]) for i, v in enumerate(lv) if v > 0)
        got = set()
        for b in w.ribbon.body.findChildren(QToolButton):  # QToolButton.menu()는 부르지 않는다 (PySide6 소유권)
            a = b.action_() if hasattr(b, "action_") else b.defaultAction()
            if a is not None and a.objectName():
                got.add(a.objectName())
            dd = getattr(b, "dropdown", None)
            if dd is not None:
                got.update(x.objectName() for x in dd.actions() if x.objectName())
        want = {n for _, cmds in groups for n, _ in cmds}
        reach_ok &= want <= got
        detail[k] = w.ribbon.group_modes()
    check("1280px 폭 리본: 오른쪽부터 축소 규칙·모든 명령 접근", rule_ok and reach_ok, str(detail))
    w.ribbon.set_tab(0)
    w.actions["ribbon.toggle"].trigger()
    check("리본 접기 (Ctrl+F1 명령) + 저장", w.ribbon.collapsed and not w.ribbon.body.isVisible()
          and str(w.settings.value(KEY_RIBBON)).lower() == "true")
    w.actions["ribbon.toggle"].trigger()
    check("리본 펼치기", not w.ribbon.collapsed and not w.ribbon.body.isHidden(),
          f"collapsed={w.ribbon.collapsed} visible={w.ribbon.body.isVisible()} hidden={w.ribbon.body.isHidden()}"
          f" parent_ok={w.ribbon.body.parent() is w.ribbon} win_visible={w.isVisible()}")
    check("단축키 정의", reg["file.open_folder"].shortcut().toString() == "Ctrl+Shift+O"
          and reg["edit.goto_offset"].shortcut().toString() == "Ctrl+G")
    check("창 제목 (작업 표시줄)", w.windowTitle() == "DICOM Tag Explorer", w.windowTitle())
    check("최소 크기 1280x720", w.minimumSize().width() == 1280 and w.minimumSize().height() == 720)

    t0 = time.perf_counter()
    w.open_paths([root], add_recent=False)
    done = wait(lambda: w.batch is not None and w.batch.finished, 120)
    check("폴더 열기 완료", done, f"{time.perf_counter() - t0:.2f}s, 파일 {len(w.files)}개")
    check("DICOM 35개", len(w.files) == 35)
    check("WSI 2개", [len(g.instances) for g in w.groups] == [14, 20], str([len(g.instances) for g in w.groups]))
    check("열기 후 WSI 탭", w.dock.tabs.currentIndex() == TAB_WSI)
    check("파일 탭 폴더 2개", w.dock.files_model.rowCount() == 2)
    check("DICOMDIR 루트 1개", len(w.dock.dir_model.roots) == 1)

    # 레이블 파일 선택
    label = next(f for f in w.files.values() if f.path.name.endswith("_label.dcm"))
    w.dock.select_key(label.key, TAB_WSI, emit=True)
    wait(lambda: w.cur_file is label, 10)
    check("Instance 선택 → Tag Tree", w.tag.model.rowCount() > 10, f"rows={w.tag.model.rowCount()}")
    check("Instance 선택 → Hex", w.raw.hex.size == label.size)
    # Tag → Hex
    nid = label.index.find_child(-1, 0x00080016)
    w.tag.select_node(nid)
    QApplication.processEvents()
    check("Tag 선택 → Hex 하이라이트", w.raw.hex.hl == (label.index.start[nid], label.index.header_len[nid],
                                                    label.index.total_len[nid]))
    check("정보 줄", "SOPClassUID" in w.raw.info.text(), w.raw.info.text().split("│")[0].strip())
    # Hex 클릭 → Tag
    hx = w.raw.hex
    hx.verticalScrollBar().setValue(0)
    y = 0 * hx.lh + hx.lh // 2
    QTest.mouseClick(hx.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(hx._hex_cell(5) + 2, y))
    QApplication.processEvents()
    cur = w.tag.current_node()
    check("Hex 클릭(오프셋 5) → Preamble 노드", cur == 0, f"node={cur}")
    hx.setFocus()
    QTest.keyClick(hx, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    check("Ctrl+End", hx.cursor == label.size - 1)
    # Ctrl+End로 커서가 Pixel Data에 들어가면 Fragment 색인이 백그라운드로 돈다. 아래 Delimiter 노드(Sequence
    # Delimitation)는 이 색인이 붙이므로 끝날 때까지 기다린다
    label_px = label.index.find_child(-1, 0x7FE00010)
    check("label Fragment 색인 완료", label_px is None or wait(lambda: not label.index.needs_fragments(label_px), 30))
    QTest.keyClick(hx, Qt.Key.Key_Home, Qt.KeyboardModifier.ControlModifier)
    check("Ctrl+Home", hx.cursor == 0)

    # 선택 행 가독성: 회색(ForegroundRole) 노드도 선택 시 HighlightedText(ink)로 그린다
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QStyleOptionViewItem
    pal = QApplication.palette()
    check("팔레트 Highlight/HighlightedText = selection/ink",
          pal.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight) == theme.color("selection")
          and pal.color(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText) == theme.color("ink"))
    from dicom_tag_explorer.core.element_index import K_ITEM_DELIM, K_SEQ_DELIM
    dn = next(i for i in range(len(label.index)) if label.index.kind[i] in (K_ITEM_DELIM, K_SEQ_DELIM))
    w.tag.select_node(dn)
    QApplication.processEvents()
    opt = QStyleOptionViewItem()
    opt.initFrom(w.tag.tree)
    mi = w.tag.model.index_of(dn, 0)
    w.tag.tree.itemDelegate().initStyleOption(opt, mi)
    from PySide6.QtWidgets import QStyle
    sel = bool(opt.state & QStyle.StateFlag.State_Selected) or w.tag.tree.selectionModel().isSelected(mi)
    opt.state |= QStyle.StateFlag.State_Selected
    w.tag.tree.itemDelegate().initStyleOption(opt, mi)
    check("선택된 Delimiter 행 글자 = ink", sel and opt.palette.color(QPalette.ColorRole.Text) == theme.color("ink"))

    # 큰 파일 (레벨 0)
    l0 = next(f for f in w.files.values() if f.path.name.endswith("_z_0_level_0.dcm"))
    t1 = time.perf_counter()
    w.dock.select_key(l0.key, TAB_WSI, emit=True)
    wait(lambda: w.cur_file is l0, 10)
    check("레벨 0 선택", w.tag.model.rowCount() > 0, f"{time.perf_counter() - t1:.2f}s")
    worst = 0.0
    t_end = time.perf_counter() + 3
    while time.perf_counter() < t_end:
        a = time.perf_counter()
        QApplication.processEvents()
        worst = max(worst, time.perf_counter() - a)
        time.sleep(0.01)
    check("레벨 0 표시 중 UI 정지 < 0.2s", worst < 0.2, f"최대 {worst * 1000:.0f} ms")
    QTest.keyClick(hx, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
    check("레벨 0 Ctrl+End", hx.cursor == l0.size - 1)
    px = l0.index.find_child(-1, 0x7FE00010)
    w.tag.tree.expand(w.tag.model.index_of(px))
    ok = wait(lambda: not l0.index.needs_fragments(px), 60)
    check("Pixel Data 펼침 → Fragment 색인", ok and w.tag.model.rowCount(w.tag.model.index_of(px)) == 20308)

    # WSI 노드
    gv = w.groups[1]
    w.dock.select_key(gv.key, TAB_WSI, emit=True)
    QApplication.processEvents()
    check("WSI 노드 → 요약표 20행", w.tag.wsi_model.rowCount() == 20)
    check("WSI 노드 → RAW 안내", w.raw.stack.currentIndex() == 1)
    check("WSI 노드 → 검색 비활성", not w.tag.search_edit.isEnabled() and not w.tag.show_only_chk.isEnabled())
    # 탭 전환 시 선택 유지
    w.dock.select_key(label.key, TAB_WSI, emit=True)
    wait(lambda: w.cur_file is label, 10)
    w.set_tab(TAB_FILES)
    QApplication.processEvents()
    cur_idx = w.dock.trees[TAB_FILES].currentIndex()
    check("탭 전환 시 같은 노드 선택", cur_idx.isValid() and w.cur_file is label)

    # DICOMDIR STUDY 레코드
    dd_key = next(iter(w.dock.dir_model.roots))
    recs = w.dir_records[dd_key]
    study = next(r for r in iter_records(recs) if r.record_type == "STUDY")
    w.set_tab(TAB_DICOMDIR)
    w._on_node_selected("record", (dd_key, study))
    wait(lambda: w.cur_file is not None and w.cur_file.key == dd_key, 10)
    QApplication.processEvents()
    check("STUDY 선택 → DICOMDIR Item 선택", w.tag.current_node() == study.node)

    # ---- 이미지 (마일스톤 4) ----
    iv = w.image.view
    w.set_tab(TAB_WSI)
    w.reveal_file(label.key)
    ok = wait(lambda: iv.pix_item is not None, 20)
    check("레이블 → 단일 이미지", ok and w.image.stack.currentWidget() is iv)
    s0 = iv.scale_factor()
    iv.zoom(1.25)
    check("확대", iv.scale_factor() > s0)
    iv.rotate_by(90)
    check("우회전 90°", iv.rotation == 90)
    w.dock.select_key(next(f for f in w.files.values() if f.path.name.endswith("_overview.dcm")).key,
                      TAB_WSI, emit=True)
    wait(lambda: iv.pix_item is not None and iv.rotation == 0, 20)
    check("다른 Instance 선택 → 0°·맞춤", iv.rotation == 0 and iv._fitted)
    l3 = next(f for f in w.files.values() if f.path.name.endswith("_z_0_level_3.dcm"))
    w.dock.select_key(l3.key, TAB_WSI, emit=True)
    ok = wait(lambda: iv.slide is not None and not iv.multi_level, 30)
    check("VOLUME L3 → 타일 모드 단일 레벨", ok and len(iv.slide.levels) == 1, iv.zoom_text())
    ok = wait(lambda: len(iv.cache) > 0 and not iv.inflight, 30)
    check("타일 로딩", ok, f"cache={len(iv.cache)}")
    w.dock.select_key(gv.key, TAB_WSI, emit=True)
    ok = wait(lambda: iv.slide is not None and iv.multi_level, 60)
    check("WSI 노드 → 피라미드 슬라이드", ok and len(iv.slide.levels) == 9, iv.zoom_text())
    lv_fit = iv.level
    t2 = time.perf_counter()
    for _ in range(30):
        iv.zoom(1.25)
        QApplication.processEvents()
    wait(lambda: not iv._timer.isActive(), 5)
    QApplication.processEvents()
    check("확대 → 레벨 자동 전환", iv.level < lv_fit, f"{lv_fit} → {iv.level}, {iv.zoom_text()}")
    ok = wait(lambda: not iv.inflight and len(iv.cache) > 0, 60)
    check("고배율 타일 로딩", ok, f"{time.perf_counter() - t2:.2f}s, 상태바 {w.zoom_label.text()}")
    check("기본 초점면 z0", iv.z == 0.0 and "z0" in iv.zoom_text())
    dd_file = w.files[dd_key]
    w.dock.select_key(dd_key, TAB_DICOMDIR, emit=True)
    wait(lambda: w.cur_file is dd_file, 10)
    wait(lambda: "no image to display" in w.image.msg.text(), 10)
    check("DICOMDIR → 이미지 없음 안내", "no image to display" in w.image.msg.text())

    # ---- 검색 (마일스톤 5) ----
    tp = w.tag
    w.set_tab(TAB_WSI)
    w.reveal_file(label.key)
    wait(lambda: w.cur_file is label, 10)
    tp.search_edit.setText("77.1.6")
    ok = wait(lambda: tp.count_label.text() == "1 / 2", 10)
    check("통합 검색 77.1.6 → 1 / 2", ok, tp.count_label.text())
    sel = tp.current_node()
    check("첫 일치로 이동 + RAW 동기화", sel in w.matches and w.raw.hex.hl is not None
          and w.raw.hex.hl[0] == label.index.start[sel])
    w.search_step(1)
    check("F3 다음 → 2 / 2", tp.count_label.text() == "2 / 2")
    w.search_step(1)
    check("순환 → 1 / 2", tp.count_label.text() == "1 / 2")
    w.search_step(-1)
    check("Shift+F3 이전 → 2 / 2", tp.count_label.text() == "2 / 2")
    tp.search_edit.setText("없는문자열xyz")
    ok = wait(lambda: tp.count_label.text() == "0 / 0", 10)
    check("0건 → 0 / 0 + danger-bg", ok and tp.search_edit.property("zero") is True)
    w.reveal_file(l0.key)
    wait(lambda: w.cur_file is l0, 10)
    tp.search_edit.setText("ZOffsetInSlideCoordinateSystem")
    t3 = time.perf_counter()
    worst = 0.0
    while time.perf_counter() - t3 < 30 and tp.count_label.text() != "1 / 20307":
        a = time.perf_counter()
        QApplication.processEvents()
        worst = max(worst, time.perf_counter() - a)
        time.sleep(0.01)
    check("L0 검색 → 1 / 20307", tp.count_label.text() == "1 / 20307",
          f"{time.perf_counter() - t3:.2f}s, UI 최대 정지 {worst * 1000:.0f} ms")
    check("검색 중 UI 정지 < 0.2s", worst < 0.2)

    # SPEC-041 Show only (TC-055 축약): 2만 건 일치에서 켜기·F3·RAW 동기화·끄기, 선택 유지
    def stall(action) -> float:
        t = time.perf_counter()
        action()
        worst_ = time.perf_counter() - t
        for _ in range(20):
            a_ = time.perf_counter()
            QApplication.processEvents()
            worst_ = max(worst_, time.perf_counter() - a_)
            time.sleep(0.005)
        return worst_
    sel0 = tp.current_node()
    s_on = stall(lambda: tp.show_only_chk.setChecked(True))
    m = tp.model
    tops = {l0.index.depth_path(x)[0] for x in w.matches}  # 일치 노드들의 최상위 조상
    top_ok = m.filtering and {m.index(r, 0).internalId() for r in range(m.rowCount())} == tops
    shown_ok = all(m.is_visible(x) for x in w.matches[:50]) and not m.is_visible(l0.index.find_child(-1, 0x00080016))
    check("Show only 켜기 → 일치·상위만, 1 / 20307 유지, 선택 유지, 정지 < 1s",
          top_ok and shown_ok and tp.count_label.text() == "1 / 20307" and tp.current_node() == sel0 and s_on < 1.0,
          f"정지 {s_on * 1000:.0f} ms")
    w.search_step(1)
    QApplication.processEvents()
    cur = tp.current_node()
    check("Show only F3 → 2 / 20307, RAW 하이라이트 = 선택",
          tp.count_label.text() == "2 / 20307"
          and w.raw.hex.hl == (l0.index.start[cur], l0.index.header_len[cur], l0.index.total_len[cur]))
    s_off = stall(lambda: tp.show_only_chk.setChecked(False))
    check("Show only 끄기 → 전체 목록 + 하이라이트, 선택 유지",
          not m.filtering and tp.current_node() == cur and len(m.matches) == 20307 and s_off < 1.0,
          f"정지 {s_off * 1000:.0f} ms")
    l0z1 = next(f for f in w.files.values() if f.path.name.endswith("_z_1_level_0.dcm"))
    w.reveal_file(l0z1.key)
    wait(lambda: w.cur_file is l0z1, 10)
    tp.search_edit.clear()
    tp.adv_btn.setChecked(True)
    tp.adv["tag"].setText("0040,074A")
    tp.adv["value"].setText("1")
    ok = wait(lambda: tp.count_label.text() == "1 / 20307", 30)
    check("상세 TAG 0040,074A AND Value 1 (z1) → 20307", ok, tp.count_label.text())
    tp.adv["tag"].setText("00G0")
    wait(lambda: tp.adv["tag"].property("invalid") is True, 5)
    check("형식 오류 TAG → danger 테두리·툴팁", tp.adv["tag"].property("invalid") is True and tp.adv["tag"].toolTip())
    # TC-053: VR UI로 결과를 줄인 뒤 패널을 접으면 통합 검색만의 결과로 돌아가고, 펼치면 다시 적용된다
    tp.clear_advanced()
    tp.search_edit.setText("ZOffsetInSlideCoordinateSystem")
    wait(lambda: tp.count_label.text() == "1 / 20307", 30)
    tp.adv["vr"].setText("UI")
    ok1 = wait(lambda: tp.count_label.text() == "0 / 0", 30)
    tp.adv_btn.setChecked(False)
    ok2 = wait(lambda: tp.count_label.text() == "1 / 20307", 30)
    tp.adv_btn.setChecked(True)
    ok3 = wait(lambda: tp.count_label.text() == "0 / 0", 30) and tp.adv["vr"].text() == "UI"
    check("접힌 상세 조건 미적용·펼치면 재적용 (TC-053)", ok1 and ok2 and ok3)
    tp.search_edit.clear()
    tp.clear_advanced()
    check("Clear → 상세 필드만 비움", not tp.adv["tag"].text() and not tp.adv["value"].text())
    tp.search_edit.setText("abc")
    w.escape()
    check("Esc 1단계 → 상세 패널 닫기", not tp.adv_btn.isChecked() and tp.search_edit.text() == "abc")
    w.escape()
    check("Esc 2단계 → 검색어 지우기", tp.search_edit.text() == "")
    wait(lambda: not tp.debounce.isActive(), 2)

    # ---- 테마 전환 (SPEC-035) ----
    w.set_theme("light")
    QApplication.processEvents()
    pal = QApplication.palette()
    check("라이트 전환: 팔레트·저장·캔버스 bg-000",
          pal.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window) == theme.color("bg-100", "light")
          and str(w.settings.value(KEY_THEME)) == "light"
          and w.image.view.backgroundBrush().color() == theme.color("bg-000", "light"))
    check("라이트 전환 후 트리 유지", len(w.files) == 35 and w.dock.wsi_model.rowCount() == 3)
    w.set_theme("dark")
    QApplication.processEvents()

    # ---- 언어 전환 (SPEC-033) ----
    w.reveal_file(label.key)
    wait(lambda: w.cur_file is label, 10)
    w.set_language("ko")
    QApplication.processEvents()
    ko_ok = (w.ribbon.tab_buttons[0].text() == "파일" and w.dock.tabs.tabText(0) == "파일"
             and tp.search_edit.placeholderText() == "모든 컬럼 검색…"
             and w.actions["file.open"].text() == "파일 열기"
             and w.dock.wsi_model.item(0, 1).text().startswith("Instance ")
             and w.titlebar.btn_close.toolTip() == "닫기")
    check("한국어 전환: 리본·Dock·검색·명령·트리 정보·타이틀바", ko_ok,
          f"{w.ribbon.tab_buttons[0].text()}|{w.dock.tabs.tabText(0)}|{tp.search_edit.placeholderText()}")
    hdr = [w.tag.model.headerData(i, Qt.Orientation.Horizontal) for i in range(7)]
    check("Tag Tree 헤더는 영어 고정", hdr == ["TAG", "VR", "VM", "Length", "Name", "Value", "Offset"])
    w.tag.show_message(w._msg_select)
    w.set_language("en")
    QApplication.processEvents()
    check("영어 복귀: 안내문·리본 재번역", w.tag.msg.text() == "Select an item in the Explorer."
          and w.ribbon.tab_buttons[0].text() == "File" and str(w.settings.value(KEY_LANGUAGE)) == "en")

    # ---- 설정 창 (SPEC-032, 038) ----
    from dicom_tag_explorer.ui.settings_dialog import PAGE_ABOUT, PAGE_LICENSE, SettingsDialog
    dlg = SettingsDialog(PAGE_LICENSE, w)
    dlg.show()
    QApplication.processEvents()
    check("설정 창 라이선스 항목: FreeType 크레딧", dlg.pages.currentIndex() == PAGE_LICENSE
          and "FreeType" in dlg.credit.text())
    check("설정 창 소스 실행 안내문", dlg.lic_dev.isVisible() and "running from source" in dlg.lic_dev.text())
    dlg.nav.setCurrentRow(PAGE_ABOUT)
    check("설정 창 정보: 버전·dev 빌드", "0.1.0" in dlg.about_info.text() and "dev" in dlg.about_info.text())
    dlg.close()

    # 영역 최대화
    w.toggle_maximize("raw")
    check("RAW 최대화", w.tag.isHidden() and w.image.isHidden())
    w.escape()
    check("Esc 복원", not w.tag.isHidden() and not w.image.isHidden())

    # ---- 타일 캐시 메모리 (L-05): L0까지 확대·이동 ----
    w.reveal_file(gv.instances[0].file.key)
    w.dock.select_key(gv.key, TAB_WSI, emit=True)
    wait(lambda: iv.slide is not None and iv.multi_level, 60)
    for _ in range(30):
        iv.zoom(1.25)
        QApplication.processEvents()
    peak = 0
    t4 = time.perf_counter()
    while time.perf_counter() - t4 < 20:
        iv.horizontalScrollBar().setValue(iv.horizontalScrollBar().value() + 400)
        iv.verticalScrollBar().setValue(iv.verticalScrollBar().value() + 250)
        wait(lambda: not iv.inflight, 2)
        peak = max(peak, iv.cache.bytes)
    check("L0 Pan 20초: 타일 캐시 ≤ 256 MiB", peak <= 256 * 1024 * 1024,
          f"최대 {peak / 2**20:.0f} MiB, {len(iv.cache)}장")

    w.close_all()
    check("모두 닫기", len(w.files) == 0)
    w.close()
    ng = [r for r in results if not r[1]]
    print(f"\n스모크 {len(results) - len(ng)}/{len(results)} 통과")
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())
