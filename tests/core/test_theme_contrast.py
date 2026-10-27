# Design System 가독성 규칙 표의 (바탕, 글자) 조합이 두 테마 모두 4.5:1 이상인지 계산으로 확인한다 (TC-042).
from __future__ import annotations

import pytest

from dicom_tag_explorer.ui.design_tokens import COLORS
from dicom_tag_explorer.ui.theme import READABILITY


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_contrast_formula():
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)


PAIRS = [(bg, fg) for bg, fgs in READABILITY for fg in fgs]


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("bg, fg", PAIRS)
def test_readability_pairs(theme, bg, fg):
    t = COLORS[theme]
    r = contrast(t[bg], t[fg])
    assert r >= 4.5, (theme, bg, fg, round(r, 2))


def test_selection_values_match_readme():
    # README 표: selection 위 ink 다크 7.0 / 라이트 12.6
    assert contrast(COLORS["dark"]["selection"], COLORS["dark"]["ink"]) == pytest.approx(7.0, abs=0.1)
    assert contrast(COLORS["light"]["selection"], COLORS["light"]["ink"]) == pytest.approx(12.6, abs=0.1)
