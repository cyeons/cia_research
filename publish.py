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


# 목차는 weekly.render()를 쓰지 않는다. 그건 메일 본문용 CSS라, 정작 링크를 거는
# 문서들은 제대로 디자인돼 있는데 목차만 맨몸이 된다.
#
# 방향: 사용자가 표준(문서 사이트 카드 그리드)을 골랐다. 아이러니 없이 정석대로 짓되
# 마감은 끝까지 간다. 밝은 쪽이 기본인 이유는 취향이 아니라 사용 장면이다 —
# 낮의 교실 PC 앞에서 차분히 읽는다. 다크는 시스템 설정을 존중하는 수준으로만 둔다.
HEAD = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>연구회 논문 읽기</title>
<meta name="color-scheme" content="light dark">
<link rel="stylesheet" as="style" crossorigin
      href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  darkMode: 'media',
  theme: { extend: {
    fontFamily: { sans: ['Pretendard Variable','Pretendard','system-ui','sans-serif'] },
    colors: {
      paper:  { DEFAULT:'#FBFBFA', dark:'#0D0F0E' },
      card:   { DEFAULT:'#FFFFFF', dark:'#151817' },
      ink:    { DEFAULT:'#18191B', dark:'#E9EBE9' },
      muted:  { DEFAULT:'#62676B', dark:'#9BA19E' },
      rule:   { DEFAULT:'#E3E5E3', dark:'#262A28' },
      accent: { DEFAULT:'#0F6E58', dark:'#4FC9AC' },
    },
  }}
}
</script>
<style>
  /* 안 그린 부분도 디자인에 속한다: 선택 영역, 캐럿, 스크롤바, 포커스 링 */
  ::selection { background:#0F6E5822; color:#18191B }
  html { caret-color:#0F6E58; scrollbar-color:#C9CDC9 transparent }
  body { -webkit-font-smoothing:antialiased; word-break:keep-all;
         font-feature-settings:"tnum" 0 }
  .tnum { font-variant-numeric:tabular-nums }

  /* 타입 스케일은 유틸리티가 아니라 시스템으로 둔다. 각 단계 1.25배 이상. */
  h1 { font-size:2.375rem; line-height:1.24; letter-spacing:-.032em; font-weight:700 }
  h2 { font-size:.875rem; line-height:1.5;  letter-spacing:-.005em; font-weight:600 }
  h3 { font-size:1.1875rem; line-height:1.5; letter-spacing:-.014em; font-weight:600 }
  .lede { font-size:1.0625rem; line-height:1.8 }
  .desc { font-size:.9375rem; line-height:1.7 }
  @media (max-width:640px){ h1 { font-size:1.875rem } }
  :focus-visible { outline:2px solid #0F6E58; outline-offset:3px; border-radius:4px }
  @media (prefers-color-scheme:dark){
    ::selection { background:#4FC9AC33; color:#E9EBE9 }
    html { caret-color:#4FC9AC; scrollbar-color:#313733 transparent }
    :focus-visible { outline-color:#4FC9AC }
  }
  @media print {
    body { background:#fff !important; color:#000 !important }
    li { break-inside:avoid }
  }
</style>
</head>
<body class="bg-paper dark:bg-paper-dark text-ink dark:text-ink-dark font-sans">
<div class="mx-auto w-full max-w-4xl px-6 sm:px-8">
"""

FOOT = """
</div>
</body>
</html>"""


def head_block(total, rounds):
    """제목 위 kicker/eyebrow는 쓰지 않는다. 제목이 스스로 버틴다."""
    return f"""
  <header class="pt-16 pb-12 sm:pt-24 sm:pb-16 border-b border-rule dark:border-rule-dark">
    <h1>연구회 논문 읽기</h1>
    <p class="lede mt-4 max-w-[62ch] text-muted dark:text-muted-dark">
      격주 월요일에 함께 읽는 논문을, 전문용어 없이 그림 위주로 풀어 쓴 글입니다.
    </p>
    <p class="mt-6 text-sm text-muted dark:text-muted-dark tnum">
      {rounds}개 회차 · 전체 {total}편
    </p>
  </header>"""


def round_block(day, items):
    return f"""
  <section class="pt-12 sm:pt-14">
    <h2 class="text-muted dark:text-muted-dark tnum">{day}</h2>
    <ul class="mt-4 grid gap-4 sm:grid-cols-2">{"".join(items)}</ul>
  </section>"""


def card(href, title, one):
    tail = (f'<p class="desc mt-2 text-muted dark:text-muted-dark">{one}</p>'
            if one else "")
    return f"""
    <li class="flex">
      <a href="{href}" class="group flex w-full flex-col rounded-lg border border-rule
             dark:border-rule-dark bg-card dark:bg-card-dark p-5 sm:p-6
             transition duration-150 hover:border-accent/50 dark:hover:border-accent-dark/50
             hover:shadow-[0_2px_16px_-6px_rgba(24,25,27,0.16)]">
        <h3 class="group-hover:text-accent dark:group-hover:text-accent-dark
                   transition-colors duration-150">{title}</h3>
        {tail}
      </a>
    </li>"""


def build_index():
    """docs/study/ 를 훑어 목차를 다시 만든다. 파일이 곧 목록이다."""
    blocks, total, rounds = [], 0, 0
    for day in sorted((d for d in ROOT.iterdir() if d.is_dir()), reverse=True):
        items = []
        for f in sorted(day.glob("*.html")):
            title, one = meta(f)
            items.append(card(f"{day.name}/{f.name}", title, one))
        if items:
            total += len(items); rounds += 1
            blocks.append(round_block(day.name, items))

    body = "".join(blocks) or """
  <p class="pt-16 pb-24 text-muted dark:text-muted-dark">
    아직 올린 글이 없습니다. <code>python publish.py &lt;파일&gt;</code> 로 첫 편을 올리세요.
  </p>"""
    foot = (f'<footer class="mt-20 border-t border-rule dark:border-rule-dark py-8 '
            f'text-xs text-muted dark:text-muted-dark tnum">갱신 {date.today()}</footer>')
    INDEX.write_text(HEAD + head_block(total, rounds) + body + foot + FOOT, encoding="utf-8")
    return total


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
