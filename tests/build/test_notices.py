# 고지 생성기(gen_notices)와 의존성 고정 검사 테스트 (TC-033, TC-034).
from __future__ import annotations

import re
from pathlib import Path

import pytest

import gen_notices as gn
from gen_notices import DistRecord, NoticeError, generate, load_policy, norm, spdx_choice

ROOT = Path(__file__).resolve().parents[2]

POLICY = """
[policy]
allowed_verdicts = ["허용", "조건부(LGPL)", "조건부(미수정)"]
allowed_spdx = ["MIT", "BSD-3-Clause", "LGPL-3.0-only"]
conditional_spdx = { "MPL-2.0" = "조건부(미수정)" }
allowed_exceptions = ["GCC-exception-3.1"]
allowed_qt_modules = ["Core", "Gui", "Widgets", "Svg"]
freetype_credit = "Portions of this software are copyright (c) The FreeType Project."

[packages."goodpkg"]
version = "1.0"
meta = "MIT"
spdx = "MIT"
verdict = "허용"

[packages."gplpkg"]
version = "1.0"
meta = "GPL-3.0-only"
spdx = "GPL-3.0-only"
verdict = "허용"

[packages."qtpkg"]
version = "6.0"
meta = "LGPL-3.0-only OR GPL-3.0-only"
spdx = "LGPL-3.0-only OR GPL-3.0-only"
verdict = "조건부(LGPL)"

[packages."held"]
version = "1.0"
meta = "Foo"
spdx = "MIT"
verdict = "보류"

[runtime."python"]
title = "Python 런타임"
spdx = "PSF-2.0"
verdict = "허용"
"""


@pytest.fixture
def env(tmp_path):
    pol = tmp_path / "policy.toml"
    pol.write_text(POLICY, encoding="utf-8")
    base = tmp_path / "python"
    base.mkdir()
    (base / "LICENSE.txt").write_text("PSF LICENSE TEXT", encoding="utf-8")
    site = tmp_path / "site"
    site.mkdir()

    def dist(name, meta, version="1.0", texts=True, files=("mod.py",)):
        paths = [str(site / name / f) for f in files]
        return DistRecord(name, version, meta, [("LICENSE", f"{name} license text")] if texts else [],
                          [gn._key(p) for p in paths], [name])

    return dict(pol=pol, base=str(base), site=site, dist=dist, out=tmp_path / "N.txt")


def run(env, dists, binaries=(), pure=()):
    return generate(list(pure), list(binaries), [], env["out"], policy_path=env["pol"], dists=dists,
                    base_prefix=env["base"], app_roots=[], app_version="0.1.0")


def bin_of(env, name, f="mod.py"):
    return [(f, str(env["site"] / name / f), "BINARY")]


def test_ok_generates_table_and_sections(env):
    d = [env["dist"]("goodpkg", "MIT"), env["dist"]("qtpkg", "LGPL-3.0-only OR GPL-3.0-only", "6.0",
                                                      files=("Qt6Core.dll",))]
    out = run(env, d, bin_of(env, "goodpkg") + bin_of(env, "qtpkg", "Qt6Core.dll"))
    text = out.read_text(encoding="utf-8")
    assert "FreeType Project" in text
    assert re.search(r"^goodpkg\s+\| 1\.0\s+\| MIT\s+\| 허용$", text, re.M)
    assert "===== goodpkg 1.0 (MIT) =====" in text
    assert "===== qtpkg 6.0 (LGPL-3.0-only) =====" in text  # OR 식은 허용 선택지를 고른다
    assert "===== Python 런타임" in text and "PSF LICENSE TEXT" in text


@pytest.mark.parametrize("case, expect", [
    ("gpl", "gplpkg"),
    ("unlisted", "newpkg"),
    ("changed", "goodpkg"),
    ("notext", "goodpkg"),
    ("held", "held"),
])
def test_failures_name_package(env, case, expect):
    mk = env["dist"]
    dists = {
        "gpl": [mk("gplpkg", "GPL-3.0-only")],
        "unlisted": [mk("newpkg", "MIT")],
        "changed": [mk("goodpkg", "BSD-3-Clause")],
        "notext": [mk("goodpkg", "MIT", texts=False)],
        "held": [mk("held", "Foo")],
    }[case]
    with pytest.raises(NoticeError) as ei:
        run(env, dists, bin_of(env, dists[0].name))
    assert expect in str(ei.value)
    assert not env["out"].exists()


def test_unowned_dll_fails(env):
    with pytest.raises(NoticeError) as ei:
        run(env, [env["dist"]("goodpkg", "MIT")], [("mystery.dll", "C:/elsewhere/mystery.dll", "BINARY")])
    assert "mystery.dll" in str(ei.value)


def test_qt_charts_fails(env):
    d = [env["dist"]("qtpkg", "LGPL-3.0-only OR GPL-3.0-only", "6.0", files=("Qt6Charts.dll",))]
    with pytest.raises(NoticeError) as ei:
        run(env, d, bin_of(env, "qtpkg", "Qt6Charts.dll"))
    assert "Qt6Charts.dll" in str(ei.value)


def test_runtime_files_are_python():
    o = gn.classify([], [("python314.dll", "C:/Py/python314.dll", "BINARY"),
                         ("vcruntime140.dll", "C:/Py/vcruntime140.dll", "BINARY")], [], [], "C:/Py", [])
    assert o.runtime and o.msvc and not o.unknown


def test_spdx_choice():
    pol = load_policy()["policy"]
    assert spdx_choice("LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only", pol, "조건부(LGPL)") == (True, "LGPL-3.0-only")
    assert spdx_choice("GPL-3.0-only", pol, "허용")[0] is False
    assert spdx_choice("GPL-3.0-or-later WITH GCC-exception-3.1", pol, "허용")[0] is True
    assert spdx_choice("GPL-3.0-or-later WITH Foo-exception", pol, "허용")[0] is False
    assert spdx_choice("MPL-2.0", pol, "허용")[0] is False
    assert spdx_choice("MPL-2.0", pol, "조건부(미수정)")[0] is True
    assert spdx_choice("BSD-3-Clause AND (MIT OR GPL-2.0-only)", pol, "허용") == (True, "BSD-3-Clause AND MIT")


def test_policy_matches_installed_runtime():
    """현재 venv의 런타임 배포판이 대장과 일치한다 (버전·메타 문자열·원문)."""
    req = [l.split("#")[0].strip() for l in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()]
    names = [norm(l.split("==")[0]) for l in req if l]
    dists = {d.key: d for d in gn.installed_dists()}
    policy = load_policy()
    o = gn.Owners(dists={n: ["x"] for n in names})
    errors, _ = gn.check(o, dists, policy)
    assert errors == []


def test_tc033_requirements_pinned_and_approved():
    policy = load_policy()
    approved = {norm(k) for k, v in policy["packages"].items() if v["verdict"] in policy["policy"]["allowed_verdicts"]}
    for fname in ("requirements.txt", "requirements-dev.txt"):
        for line in (ROOT / fname).read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip()
            if line:
                assert re.fullmatch(r"[A-Za-z0-9._-]+==[0-9][\w.]*", line), (fname, line)
    runtime = {norm(l.split("==")[0]) for l in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
               if l.split("#")[0].strip()}
    assert runtime <= approved, runtime - approved
    for banned in ("pyside6", "pyside6-addons", "imagecodecs"):
        assert banned not in runtime
