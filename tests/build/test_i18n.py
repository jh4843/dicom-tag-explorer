# 번역 파일 검사 (TC-041): 추출 원문이 모두 완료된 한국어 번역으로 있고, 미완료가 있으면 release가 실패한다.
from __future__ import annotations

import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import i18n as tool

FIXED_TERMS = ("Tag", "VR", "VM", "Transfer Syntax", "SOP Class", "UID", "Instance", "WSI", "DICOMDIR",
               "Item", "Sequence", "Fragment", "Preamble", "Offset", "RAW", "Hex", "VOLUME", "TAG")


def messages(ts: Path) -> dict[tuple[str, str], ET.Element]:
    out = {}
    for ctx in ET.parse(ts).getroot().iter("context"):
        for m in ctx.iter("message"):
            out[(ctx.findtext("name"), m.findtext("source"))] = m
    return out


def test_all_sources_translated(tmp_path):
    tmp_ts = tmp_path / "extract_ko.ts"
    tool.lupdate(tmp_ts)
    extracted = set(messages(tmp_ts))
    committed = messages(tool.I18N / tool.KO)
    assert extracted, "추출된 문자열이 없다"
    assert extracted <= set(committed), extracted - set(committed)
    assert tool.unfinished(tool.I18N / tool.KO) == []


def test_fixed_terms_stay_english():
    for (ctx, src), m in messages(tool.I18N / tool.KO).items():
        t = m.find("translation")
        text = " ".join(n.text or "" for n in t.iter("numerusform")) or (t.text or "")
        for term in FIXED_TERMS:
            if re.search(rf"\b{re.escape(term)}\b", src):
                assert term in text, (ctx, src, text, term)


def test_release_builds_qm(tmp_path):
    for name in (tool.KO, tool.EN):
        shutil.copy(tool.I18N / name, tmp_path / name)
    assert tool.release(tmp_path) == 0
    assert (tmp_path / "dicom_tag_explorer_ko.qm").stat().st_size > 0
    assert (tmp_path / "dicom_tag_explorer_en.qm").stat().st_size > 0


def test_release_fails_on_unfinished(tmp_path):
    for name in (tool.KO, tool.EN):
        shutil.copy(tool.I18N / name, tmp_path / name)
    ko = tmp_path / tool.KO
    tree = ET.parse(ko)
    t = next(tree.getroot().iter("translation"))
    t.set("type", "unfinished")
    tree.write(ko, encoding="utf-8", xml_declaration=True)
    assert tool.release(tmp_path) == 1


def test_english_plurals():
    msgs = messages(tool.I18N / tool.EN)
    assert msgs
    for m in msgs.values():
        assert m.get("numerus") == "yes"
        forms = [n.text for n in m.iter("numerusform")]
        assert len(forms) == 2 and all(forms)
