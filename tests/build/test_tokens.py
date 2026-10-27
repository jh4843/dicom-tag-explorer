# 토큰 생성기(gen_tokens)와 생성 결과 design_tokens.py 검사 (TC-042).
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

import gen_tokens
from dicom_tag_explorer.ui import design_tokens as T

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "docs" / "design-system" / "tokens.json"


def data():
    return json.loads(SRC.read_text(encoding="utf-8"))


def test_check_matches_committed_file():
    assert gen_tokens.main(["--check"]) == 0


def test_seventy_colors_resolved_in_both_themes():
    assert len(T.PALETTE) == 40 and len(T.USAGE) == 30
    for th in ("dark", "light"):
        assert len(T.COLORS[th]) == 70
        assert all(re.fullmatch(r"#[0-9a-f]{6}", v) for v in T.COLORS[th].values())
    # 2단 별칭: caption-hover → {bg-400} → {neutral-700 / neutral-150}
    assert T.COLORS["dark"]["caption-hover"] == T.COLORS["dark"]["neutral-700"]
    assert T.COLORS["light"]["caption-hover"] == T.COLORS["light"]["neutral-150"]
    assert T.COLORS["light"]["selection-inactive"] == T.COLORS["light"]["neutral-150"]


def test_missing_alias_fails(tmp_path):
    d = data()
    tok = next(t for t in d["color"]["tokens"] if t["name"] == "ink")
    tok["value"]["dark"] = "{no-such-token}"
    with pytest.raises(gen_tokens.TokenError, match="no-such-token"):
        gen_tokens.generate(d)
    src = tmp_path / "tokens.json"
    src.write_text(json.dumps(d), encoding="utf-8")
    assert gen_tokens.main(["--check", "--src", str(src)]) == 1


def test_cycle_fails():
    d = copy.deepcopy(data())
    a = next(t for t in d["color"]["tokens"] if t["name"] == "bg-100")
    b = next(t for t in d["color"]["tokens"] if t["name"] == "bg-200")
    a["value"]["light"] = "{bg-200}"
    b["value"]["light"] = "{bg-100}"
    with pytest.raises(gen_tokens.TokenError, match="순환"):
        gen_tokens.generate(d)


def test_fonts_and_sizes():
    assert T.FONT_FAMILIES["mono"][0] == "Consolas"
    assert set(T.FONT_STYLES) == {"title", "body", "body-strong", "caption", "label", "mono", "mono-sm"}
    assert T.SIZE["size-titlebar"] == 32 and T.SIZE["size-row"] == 22
