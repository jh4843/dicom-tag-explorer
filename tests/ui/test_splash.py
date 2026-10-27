# 시작 화면 테스트: 단계 표시, 논리 크기 고정, 소수 배율에서 아이콘을 벡터로 선명하게 그리는지.
from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter

from dicom_tag_explorer.ui import theme
from dicom_tag_explorer.ui.splash import HEIGHT, LOGO, STEPS, WIDTH, Splash, _Logo


def test_steps_update_counter_and_bar(qapp):
    theme.apply(qapp, "dark")
    s = Splash("0.1.0")
    assert s.status.text() == "Loading…"
    assert s.counter.text() == f"1 / {STEPS}" and s.bar.value() == 1
    for n in range(2, STEPS + 1):
        s.step(n)
        assert s.counter.text() == f"{n} / {STEPS}" and s.bar.value() == n
    s.step(STEPS + 3)  # 범위를 넘으면 마지막 단계에 머문다
    assert s.counter.text() == f"{STEPS} / {STEPS}"
    assert (s.width(), s.height()) == (WIDTH, HEIGHT)  # 논리 픽셀. 배율은 Qt가 곱한다


def test_logo_is_sharp_at_fractional_scale(qapp):
    logo = _Logo()
    for dpr in (1.0, 1.25, 1.5, 2.0):
        side = round(LOGO * dpr)
        img = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(0)
        p = QPainter(img)
        logo._renderer.render(p, QRectF(logo.rect()))  # paintEvent와 같은 호출
        p.end()
        # 가운데(아이콘 바탕)가 칠해졌고 가장자리 모서리는 둥근 바깥이라 비어 있다 = 물리 픽셀 크기로 그렸다
        assert img.pixelColor(side // 2, side // 2).alpha() == 255
        assert img.pixelColor(0, 0).alpha() == 0
