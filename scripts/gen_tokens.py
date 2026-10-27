# docs/design-system/tokens.json에서 별칭을 끝까지 풀어 ui/design_tokens.py를 생성하고, --check로 차이를 검사한다.
"""사용법:
    python scripts/gen_tokens.py            # ui/design_tokens.py를 다시 쓴다
    python scripts/gen_tokens.py --check    # 커밋된 파일과 생성 결과가 다르면 종료 코드 1

Spec v0.1.0 2.8.1. 앱은 실행 중에 JSON을 읽지 않는다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "design-system" / "tokens.json"
OUT = ROOT / "src" / "dicom_tag_explorer" / "ui" / "design_tokens.py"
ALIAS = re.compile(r"^\{([A-Za-z0-9_-]+)\}$")
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
GENERIC_FAMILIES = {"system-ui", "sans-serif", "serif", "monospace", "ui-monospace"}


class TokenError(Exception):
    pass


def _px(v: str) -> int:
    v = str(v).strip()
    if v.endswith("px"):
        v = v[:-2]
    return int(float(v))


def resolve_colors(data: dict) -> dict[str, dict[str, str]]:
    """테마별 {토큰: hex}. 팔레트(단일 값)는 두 테마에 같은 값으로 들어간다."""
    themes = [t["id"] for t in data["color"]["themes"]]
    raw: dict[str, dict[str, str]] = {th: {} for th in themes}
    for tok in data["color"]["tokens"]:
        v = tok["value"]
        for th in themes:
            raw[th][tok["name"]] = v if isinstance(v, str) else v[th]
    out: dict[str, dict[str, str]] = {}
    for th in themes:
        table = raw[th]
        done: dict[str, str] = {}

        def resolve(name: str, stack: tuple[str, ...]) -> str:
            if name in done:
                return done[name]
            if name not in table:
                raise TokenError(f"[{th}] 없는 별칭: {{{name}}} (경로 {' -> '.join(stack)})")
            if name in stack:
                raise TokenError(f"[{th}] 순환 별칭: {' -> '.join(stack + (name,))}")
            v = table[name]
            m = ALIAS.match(v)
            if m:
                val = resolve(m.group(1), stack + (name,))
            elif HEX.match(v):
                val = v.lower()
            else:
                raise TokenError(f"[{th}] {name}: hex도 별칭도 아닌 값 {v!r}")
            done[name] = val
            return val

        out[th] = {name: resolve(name, ()) for name in table}
    return out


def families(spec: str) -> list[str]:
    out = []
    for part in spec.split(","):
        f = part.strip().strip('"').strip("'")
        if f and f not in GENERIC_FAMILIES:
            out.append(f)
    return out


def generate(data: dict) -> str:
    colors = resolve_colors(data)
    fams = {k: families(v) for k, v in data["type"]["families"].items()}
    styles = {}
    for g in data["type"]["groups"]:
        for s in g["styles"]:
            styles[s["name"]] = {"family": g["family"], "size": _px(s["fontSize"]),
                                 "line": _px(s["lineHeight"]), "weight": int(s.get("fontWeight", 400))}
    space = {t["name"]: _px(t["value"]) for t in data["spacing"]["tokens"]}
    radius = {t["name"]: _px(t["value"]) for t in data["radius"]["tokens"]}
    size = {t["name"]: _px(t["value"]) for t in data["size"]["tokens"]}
    shadow = {t["name"]: t["value"] for t in data["shadow"]["tokens"]}
    palette = [t["name"] for t in data["color"]["tokens"] if isinstance(t["value"], str)]
    usage = [t["name"] for t in data["color"]["tokens"] if not isinstance(t["value"], str)]

    def block(name, value) -> str:
        return f"{name} = {json.dumps(value, ensure_ascii=False, indent=4)}\n"

    lines = [
        "# 자동 생성, 직접 수정 금지. scripts/gen_tokens.py가 docs/design-system/tokens.json에서 만든다.\n",
        f'"""Design System {data.get("name", "")} 토큰 v{data.get("version", "")}. 별칭은 생성 시점에 모두 풀었다."""\n',
        "\n",
        block("THEMES", list(colors)),
        block("PALETTE", palette),
        block("USAGE", usage),
        block("COLORS", colors),
        block("FONT_FAMILIES", fams),
        block("FONT_STYLES", styles),
        block("SPACE", space),
        block("RADIUS", radius),
        block("SIZE", size),
        block("SHADOW", shadow),
    ]
    return "\n".join(x.rstrip("\n") for x in lines) + "\n"


def main(argv: list[str]) -> int:
    src = SRC
    if "--src" in argv:
        src = Path(argv[argv.index("--src") + 1])
    try:
        text = generate(json.loads(src.read_text(encoding="utf-8")))
    except TokenError as e:
        print("토큰 생성 실패:", e)
        return 1
    if "--check" in argv:
        cur = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if cur != text:
            print(f"{OUT}가 tokens.json과 다릅니다. scripts/gen_tokens.py를 실행해 다시 생성하세요.")
            return 1
        print("design_tokens.py 최신")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("생성:", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
