# Tag Tree 컬럼 폭 회귀 테스트: 사용자가 바꾼 폭은 다른 파일을 선택하거나 메시지·WSI 페이지를 거쳐도 유지된다.
from __future__ import annotations

from dicom_factory import long_text_file, nested_file
from dicom_tag_explorer.core.dicom_file import DicomFile


def test_user_column_widths_survive_file_switch(qapp, tmp_path):
    from dicom_tag_explorer.ui.tag_panel import TagPanel

    f1 = DicomFile(nested_file(tmp_path / "a.dcm")).load()
    f2 = DicomFile(long_text_file(tmp_path / "b.dcm", "x" * 300)).load()
    panel = TagPanel()
    try:
        h = panel.tree.header()
        panel.show_file(f1)
        default = h.sectionSize(5)
        h.resizeSection(5, default + 77)
        h.resizeSection(0, 150)
        panel.show_file(f2)  # 다른 파일 선택
        assert (h.sectionSize(5), h.sectionSize(0)) == (default + 77, 150)
        panel.show_message("none")  # 파일 없는 페이지를 거쳐도 유지
        panel.show_file(f1)
        assert (h.sectionSize(5), h.sectionSize(0)) == (default + 77, 150)
    finally:
        panel.deleteLater()
