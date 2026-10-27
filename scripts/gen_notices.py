# 번들 내용으로 THIRD_PARTY_NOTICES.txt를 생성하고 대장 밖·금지·보류 라이선스가 있으면 빌드를 실패시킨다.
"""PyInstaller spec에서 Analysis 직후 호출한다 (Spec v0.1.0 2.7, SPEC-028).

    from gen_notices import generate, NoticeError
    generate(a.pure, a.binaries, a.datas, out_path)

단독 실행(`python scripts/gen_notices.py OUT`)은 현재 환경의 런타임 의존성 전체로 같은 검사를 한다.
"""
from __future__ import annotations

import importlib.metadata as md
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging"
POLICY = PACKAGING / "license_policy.toml"
APP_ROOTS = [ROOT / "src", ROOT / "scripts", ROOT / "packaging"]
LICENSE_FILE_RE = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE)([._-].*)?$", re.I)
MSVC_RE = re.compile(r"^(vcruntime140(_1)?|msvcp140(_\d|_atomic_wait|_codecvt_ids)?|concrt140|vccorlib140)\.dll$", re.I)
QT_DLL_RE = re.compile(r"^Qt6(\w+?)\.dll$", re.I)
HEADER_FMT = "===== {name} {version} ({license}) ====="


class NoticeError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _key(p) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


@dataclass
class DistRecord:
    """배포판 하나의 메타데이터. 테스트에서는 직접 만들어 주입한다."""
    name: str
    version: str
    meta: str  # meta_license() 결과
    texts: list[tuple[str, str]]  # (파일 이름, 원문)
    files: list[str] = field(default_factory=list)  # 설치 파일 절대 경로
    top_levels: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return norm(self.name)


def meta_license(m) -> str:
    """License-Expression → License 첫 줄(파일 참조가 아니면) → Classifier 순서."""
    le = (m.get("License-Expression") or "").strip()
    if le:
        return le
    lic = (m.get("License") or "").strip()
    if lic:
        first = " ".join(lic.splitlines()[0].split())
        if not re.fullmatch(r"(LICEN[CS]E|COPYING)(\.\w+)?", first, re.I):
            return first
    cls = [c.split("::")[-1].strip() for c in (m.get_all("Classifier") or []) if c.startswith("License ::")]
    return ("Classifier: " + "; ".join(cls)) if cls else ""


def installed_dists() -> list[DistRecord]:
    tops = md.packages_distributions()
    by_dist: dict[str, list[str]] = {}
    for top, names in tops.items():
        for n in names:
            by_dist.setdefault(norm(n), []).append(top)
    out = []
    for d in md.distributions():
        name = d.metadata["Name"]
        files, texts = [], []
        for f in d.files or []:
            p = d.locate_file(f)
            files.append(_key(p))
            parts = str(f).replace("\\", "/").split("/")
            if ".dist-info" in parts[0] and LICENSE_FILE_RE.match(parts[-1]):
                try:
                    texts.append(("/".join(parts[1:]), Path(p).read_text(encoding="utf-8", errors="replace")))
                except OSError:
                    pass
        out.append(DistRecord(name, d.version, meta_license(d.metadata), texts, files, by_dist.get(norm(name), [])))
    return out


@dataclass
class Owners:
    dists: dict[str, list[str]] = field(default_factory=dict)  # dist key → 번들 파일 예시
    runtime: list[str] = field(default_factory=list)
    msvc: list[str] = field(default_factory=list)
    app: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    qt_modules: dict[str, str] = field(default_factory=dict)  # 모듈 → 파일


def _under(path: str, roots: list[str]) -> bool:
    return any(path == r or path.startswith(r.rstrip("\\/") + os.sep) for r in roots)


def classify(pure, binaries, datas, dists: list[DistRecord], base_prefix: str, app_roots: list[Path]) -> Owners:
    file_owner: dict[str, str] = {}
    top_owner: dict[str, str] = {}
    for d in dists:
        for f in d.files:
            file_owner[f] = d.key
        for t in d.top_levels:
            top_owner.setdefault(t, d.key)
    base = [_key(base_prefix)]
    apps = [_key(p) for p in app_roots]
    o = Owners()

    def own(key: str, label: str):
        o.dists.setdefault(key, []).append(label)

    app_tops = {"dicom_tag_explorer"}
    for entry in pure:
        modname, path = entry[0], entry[1]
        top = modname.split(".")[0]
        k = _key(path) if path and path != "-" else ""  # '-'는 namespace 패키지 (파일 없음)
        if k and k in file_owner:
            own(file_owner[k], modname)
        elif k and _under(k, apps):
            o.app.append(modname)
        elif k and _under(k, base):
            o.runtime.append(modname)
        elif not k and top in app_tops:
            o.app.append(modname)
        elif not k and top in top_owner:
            own(top_owner[top], modname)
        else:
            o.unknown.append(f"{modname} ({path})")
    for entry in list(binaries) + list(datas):
        dest, src = entry[0], entry[1]
        k = _key(src)
        base_name = Path(dest).name
        m = QT_DLL_RE.match(base_name)
        if m:
            o.qt_modules[m.group(1)] = dest
        if MSVC_RE.match(base_name):
            o.msvc.append(dest)
            continue
        if k in file_owner:
            own(file_owner[k], dest)
        elif base_name == "base_library.zip":
            o.runtime.append(dest)  # PyInstaller가 표준 라이브러리로 만드는 묶음
        elif _under(k, apps):
            o.app.append(dest)
        elif _under(k, base):
            o.runtime.append(dest)
        else:
            o.unknown.append(f"{dest} ({src})")
    return o


# ---- SPDX ----
def _tokens(expr: str) -> list[str]:
    return re.findall(r"\(|\)|[A-Za-z0-9.+\-]+", expr)


def spdx_choice(expr: str, policy: dict, verdict: str) -> tuple[bool, str]:
    """(허용 여부, 선택한 라이선스 식). OR는 허용 가능한 첫 선택지를 고른다."""
    allowed = set(policy["allowed_spdx"])
    cond = policy.get("conditional_spdx", {})
    excs = set(policy.get("allowed_exceptions", []))
    toks = _tokens(expr)
    pos = 0

    def peek():
        return toks[pos] if pos < len(toks) else None

    def take():
        nonlocal pos
        pos += 1
        return toks[pos - 1]

    def atom():
        if peek() == "(":
            take()
            r = or_expr()
            if peek() == ")":
                take()
            return r
        lic = take()
        if peek() == "WITH":
            take()
            exc = take()
            return (exc in excs, f"{lic} WITH {exc}")
        ok = lic in allowed or cond.get(lic) == verdict
        return (ok, lic)

    def and_expr():
        ok, s = atom()
        parts = [s]
        while peek() == "AND":
            take()
            o2, s2 = atom()
            ok = ok and o2
            parts.append(s2)
        return (ok, " AND ".join(parts))

    def or_expr():
        alts = [and_expr()]
        while peek() == "OR":
            take()
            alts.append(and_expr())
        for ok, s in alts:
            if ok:
                return (True, s)
        return (False, " OR ".join(s for _, s in alts))

    if not toks:
        return (False, "")
    return or_expr()


def load_policy(path: Path = POLICY) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def check(o: Owners, dists: dict[str, DistRecord], policy: dict) -> tuple[list[str], dict[str, str]]:
    """(오류 목록, dist key → 선택 라이선스)."""
    errors: list[str] = []
    chosen: dict[str, str] = {}
    pk = {norm(k): v for k, v in policy.get("packages", {}).items()}
    verdicts = set(policy["policy"]["allowed_verdicts"])
    for key, files in sorted(o.dists.items()):
        d = dists[key]
        ent = pk.get(key)
        if ent is None:
            errors.append(f"대장에 없음: {d.name} {d.version} (예: {files[0]})")
            continue
        if ent["verdict"] not in verdicts:
            errors.append(f"판정이 '{ent['verdict']}'라 배포할 수 없음: {d.name} {d.version}")
            continue
        if ent.get("version") != d.version:
            errors.append(f"대장 버전과 다름 (재확인 필요): {d.name} 설치 {d.version}, 대장 {ent.get('version')}")
        if not d.meta:
            errors.append(f"라이선스 미표기: {d.name} {d.version}")
        elif d.meta != ent.get("meta"):
            errors.append(f"라이선스 문자열 변경 (재확인 필요): {d.name} {d.version} 메타 '{d.meta}', 대장 '{ent.get('meta')}'")
        ok, sel = spdx_choice(ent.get("spdx", ""), policy["policy"], ent["verdict"])
        if not ok:
            errors.append(f"금지 또는 미승인 라이선스: {d.name} {d.version} ({ent.get('spdx')})")
        chosen[key] = sel
        if not d.texts and not ent.get("extra_texts"):
            errors.append(f"라이선스 원문 파일을 찾지 못함: {d.name} {d.version}")
    for u in o.unknown:
        errors.append(f"소유 배포판을 알 수 없는 파일: {u}")
    allowed_qt = set(policy["policy"]["allowed_qt_modules"])
    for mod, f in sorted(o.qt_modules.items()):
        if mod not in allowed_qt:
            errors.append(f"허용 목록 밖 Qt 모듈: Qt6{mod}.dll ({f})")
    return errors, chosen


def _msvc_conditions(base_prefix: str) -> str:
    text = Path(base_prefix, "LICENSE.txt").read_text(encoding="utf-8", errors="replace")
    i = text.find("Additional Conditions for this Windows binary build")
    if i < 0:
        return ""
    j = text.find("\n" + "-" * 40, i + 60)
    return text[i:j if j > 0 else None].strip()


def render(o: Owners, dists: dict[str, DistRecord], policy: dict, chosen: dict[str, str],
           base_prefix: str, app_name: str, app_version: str) -> str:
    pol = policy["policy"]
    pk = {norm(k): v for k, v in policy.get("packages", {}).items()}
    rt = policy.get("runtime", {})
    rows = []  # (이름, 버전, 라이선스, 판정, 본문)
    order = [norm(k) for k in policy.get("packages", {})]
    for key in sorted(o.dists, key=lambda k: order.index(k) if k in order else 999):
        d, ent = dists[key], pk[key]
        body = []
        if ent.get("note"):
            body.append(ent["note"])
        for name, txt in d.texts:
            body.append(f"--- {name} ---\n{txt.strip()}")
        for rel in ent.get("extra_texts", []):
            p = PACKAGING / rel
            body.append(f"--- {p.name} ---\n{p.read_text(encoding='utf-8').strip()}")
        rows.append((ent.get("title", d.name), d.version, chosen[key], ent["verdict"], "\n\n".join(body)))
    py = rt.get("python", {})
    py_ver = ".".join(map(str, sys.version_info[:3]))
    py_text = Path(base_prefix, "LICENSE.txt").read_text(encoding="utf-8", errors="replace").strip()
    rows.append((py.get("title", "Python 런타임"), py_ver, py.get("spdx", "PSF-2.0"), py.get("verdict", "허용"),
                 f"--- LICENSE.txt ---\n{py_text}"))
    if o.msvc:
        ms = rt.get("msvc", {})
        body = "\n\n".join(x for x in (ms.get("note", ""), "번들 파일: " + ", ".join(sorted({Path(f).name for f in o.msvc})),
                                         _msvc_conditions(base_prefix)) if x)
        rows.append((ms.get("title", "Microsoft Visual C++ 런타임"), ms.get("version", "14.x"),
                     ms.get("spdx", ""), ms.get("verdict", ""), body))
    w0 = max(len(r[0]) for r in rows)
    w1 = max(len(r[1]) for r in rows)
    w2 = max(len(r[2]) for r in rows)
    lines = [f"{app_name} {app_version} - THIRD-PARTY NOTICES",
             f"빌드 시 번들 내용으로 자동 생성됨 ({date.today().isoformat()}).",
             "",
             pol.get("freetype_credit", ""),
             "",
             f"{'이름':<{w0}} | {'버전':<{w1}} | {'라이선스':<{w2}} | 판정",
             f"{'-' * w0}-+-{'-' * w1}-+-{'-' * w2}-+-{'-' * 12}"]
    for r in rows:
        lines.append(f"{r[0]:<{w0}} | {r[1]:<{w1}} | {r[2]:<{w2}} | {r[3]}")
    lines.append("")
    for r in rows:
        lines += ["", HEADER_FMT.format(name=r[0], version=r[1], license=r[2]), "", r[4]]
    return "\n".join(lines).rstrip() + "\n"


def generate(pure, binaries, datas, out_path: Path | str, policy_path: Path = POLICY,
             dists: list[DistRecord] | None = None, base_prefix: str | None = None,
             app_roots: list[Path] | None = None, app_version: str | None = None) -> Path:
    """검사에 실패하면 NoticeError를 던지고 파일을 쓰지 않는다."""
    policy = load_policy(policy_path)
    dists = installed_dists() if dists is None else dists
    base_prefix = base_prefix or sys.base_prefix
    if app_version is None:
        sys.path.insert(0, str(ROOT / "src"))
        from dicom_tag_explorer import __version__ as app_version
    o = classify(pure, binaries, datas, dists, base_prefix, app_roots or APP_ROOTS)
    by_key = {d.key: d for d in dists}
    errors, chosen = check(o, by_key, policy)
    if errors:
        raise NoticeError(errors)
    text = render(o, by_key, policy, chosen, base_prefix, "DICOM Tag Explorer", app_version)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out


def _runtime_requirements() -> list[str]:
    names = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            names.append(line.split("==")[0].strip())
    return names


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else ROOT / "build" / "THIRD_PARTY_NOTICES.txt"
    # 단독 실행: requirements.txt의 런타임 배포판이 모두 번들된다고 보고 검사한다
    dists = installed_dists()
    want = {norm(n) for n in _runtime_requirements()}
    binaries = [(Path(f).name, f, "BINARY") for d in dists if d.key in want for f in d.files[:1]]
    try:
        generate([], binaries, [], out, dists=dists)
    except NoticeError as e:
        print("라이선스 검사 실패:", *e.errors, sep="\n  ")
        return 1
    print("생성:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
