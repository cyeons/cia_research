"""연구회에 공유할 ELI5 요약본을 웹에 올린다.

    python publish.py eli5/260921/*.html            # 오늘 날짜로
    python publish.py --date 2026-09-22 eli5/260921/*.html

eli5/ 는 .gitignore에 있다(개인 정독 노트). 그중 고른 것만 docs/study/ 로 복사해
공개한다 — 무엇을 공유할지는 내가 하나씩 정한다는 뜻이다.

올라가는 곳: https://<계정>.github.io/<저장소>/study/
"""
import re, shutil, sys, webbrowser
from datetime import date
from pathlib import Path

import weekly
from theories import name_slug

ROOT = Path("docs/study")
INDEX = ROOT / "index.html"


def meta(path):
    """제목과 한 줄 소개를 파일에서 읽는다."""
    s = path.read_text(encoding="utf-8")
    h1 = re.search(r"<h1>(.*?)</h1>", s, re.S)
    title = re.sub(r"<[^>]+>", "", h1.group(1)).strip() if h1 else path.stem
    callout = re.search(r'class="callout"[^>]*>(.*?)</div>', s, re.S)
    one = re.sub(r"<[^>]+>", " ", callout.group(1)) if callout else ""
    return title, " ".join(one.split())[:140]


def build_index():
    """docs/study/ 를 훑어 목차를 다시 만든다. 파일이 곧 목록이다."""
    rows = []
    for day in sorted((d for d in ROOT.iterdir() if d.is_dir()), reverse=True):
        items = []
        for f in sorted(day.glob("*.html")):
            title, one = meta(f)
            items.append(
                f'<li><a href="{day.name}/{f.name}">{title}</a>'
                + (f"<br><span class='num'>{one}</span>" if one else "") + "</li>")
        if items:
            rows.append(f"<h2>{day.name}</h2><ul>{''.join(items)}</ul>")

    INDEX.write_text(weekly.render(
        '<p style="font-size:.9em">연구회에서 함께 읽는 논문 요약입니다. '
        '각 항목은 그림 위주로 풀어 쓴 한 장짜리 설명으로 이어집니다.</p>'
        + ("".join(rows) or "<p>아직 올린 글이 없습니다.</p>"),
        title="연구회 논문 읽기"), encoding="utf-8")
    return sum(len(list(d.glob("*.html"))) for d in ROOT.iterdir() if d.is_dir())


def main():
    args = sys.argv[1:]
    day = date.today().isoformat()
    if "--date" in args:
        i = args.index("--date")
        day = args[i + 1]
        args = args[:i] + args[i + 2:]
    files = [Path(a) for a in args if not a.startswith("--")]
    if not files:
        sys.exit(__doc__)

    out = ROOT / day
    out.mkdir(parents=True, exist_ok=True)
    for f in files:
        if not f.is_file():
            sys.exit(f"파일이 없습니다: {f}")
        title, _ = meta(f)
        # 원본 파일명은 경로가 그대로 박혀 있어 읽을 수 없다. 제목으로 다시 짓는다.
        dest = out / f"{name_slug(title)}.html"
        shutil.copyfile(f, dest)
        print(f"  {title}\n    -> {dest}", file=sys.stderr)

    total = build_index()
    print(f"목차 갱신: {INDEX} (전체 {total}편)", file=sys.stderr)
    if "--no-open" not in sys.argv:
        webbrowser.open(INDEX.resolve().as_uri())


if __name__ == "__main__":
    main()
