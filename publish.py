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
# 문서들은 제대로 디자인돼 있는데 목차만 맨몸이 된다. Pretendard + Tailwind로 따로 짠다.
HEAD = """<!doctype html>
<html lang="ko" class="scroll-smooth">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>연구회 논문 읽기</title>
<link rel="stylesheet" as="style" crossorigin
      href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  darkMode: 'media',
  theme: { extend: {
    fontFamily: { sans: ['Pretendard Variable','Pretendard','system-ui','sans-serif'] },
    colors: {
      paper:  { DEFAULT:'#FBFAF7', dark:'#0E1211' },
      card:   { DEFAULT:'#FFFFFF', dark:'#171C1A' },
      ink:    { DEFAULT:'#151A18', dark:'#E8EDE9' },
      muted:  { DEFAULT:'#6B7671', dark:'#8FA098' },
      rule:   { DEFAULT:'#E4E5DF', dark:'#262E2A' },
      accent: { DEFAULT:'#0E6B57', dark:'#54C9AC' },
    },
    letterSpacing: { tightest: '-0.035em' },
  }}
}
</script>
<style>
  body { -webkit-font-smoothing: antialiased; word-break: keep-all; }
  @media print {
    body { background:#fff !important; color:#000 !important; }
    a { break-inside: avoid; }
    .no-print { display:none }
  }
</style>
</head>
<body class="bg-paper dark:bg-paper-dark text-ink dark:text-ink-dark font-sans antialiased">
<div class="mx-auto w-full max-w-3xl px-5 sm:px-8">
"""

FOOT = """
</div>
</body>
</html>"""


def hero(total, rounds):
    return f"""
  <header class="pt-20 pb-14 sm:pt-28 sm:pb-20">
    <p class="text-[0.7rem] font-semibold uppercase tracking-[0.2em] text-accent dark:text-accent-dark">
      초등 컴퓨터교육 · AI교육 연구회
    </p>
    <h1 class="mt-5 text-[2.1rem] sm:text-[3.1rem] font-bold leading-[1.12] tracking-tightest text-balance">
      함께 읽는 논문,<br class="hidden sm:block"> 그림으로 풀어서.
    </h1>
    <p class="mt-6 max-w-xl text-[1.02rem] leading-[1.8] text-muted dark:text-muted-dark">
      격주 월요일마다 한 편씩. 전문용어 없이, 큰 그림부터.
      제목을 누르면 그 논문의 한 장짜리 설명이 열립니다.
    </p>
    <div class="mt-9 flex items-center gap-3 text-sm text-muted dark:text-muted-dark">
      <span class="inline-flex items-center rounded-full border border-rule dark:border-rule-dark
                   px-3 py-1 font-medium tabular-nums">{rounds}회차</span>
      <span class="inline-flex items-center rounded-full border border-rule dark:border-rule-dark
                   px-3 py-1 font-medium tabular-nums">{total}편</span>
    </div>
  </header>"""


def round_block(day, items):
    cards = "".join(items)
    return f"""
  <section class="pb-16">
    <div class="sticky top-0 z-10 -mx-5 sm:-mx-8 px-5 sm:px-8 py-4
                bg-paper/85 dark:bg-paper-dark/85 backdrop-blur
                flex items-baseline gap-4">
      <h2 class="text-[0.95rem] font-semibold tabular-nums tracking-tight">{day}</h2>
      <span class="h-px flex-1 bg-rule dark:bg-rule-dark"></span>
      <span class="text-xs text-muted dark:text-muted-dark tabular-nums">{len(items)}편</span>
    </div>
    <ul class="mt-5 space-y-4">{cards}</ul>
  </section>"""


def card(href, title, one):
    tail = (f'<p class="mt-2.5 text-[0.93rem] leading-[1.75] text-muted dark:text-muted-dark">{one}</p>'
            if one else "")
    return f"""
    <li>
      <a href="{href}" class="group block rounded-xl border border-rule dark:border-rule-dark
             bg-card dark:bg-card-dark p-6 sm:p-7 transition
             hover:-translate-y-0.5 hover:border-accent/60 dark:hover:border-accent-dark/60
             hover:shadow-[0_8px_30px_-12px_rgba(0,0,0,0.18)]
             focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2
             focus-visible:outline-accent dark:focus-visible:outline-accent-dark">
        <h3 class="text-[1.12rem] sm:text-[1.2rem] font-semibold leading-[1.45] tracking-tight text-balance">
          {title}
        </h3>
        {tail}
        <span class="mt-4 inline-flex items-center gap-1.5 text-[0.82rem] font-medium
                     text-accent dark:text-accent-dark">
          읽기
          <svg viewBox="0 0 16 16" class="h-3.5 w-3.5 transition-transform group-hover:translate-x-1"
               fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </span>
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

    body = "".join(blocks) or (
        '<p class="pb-20 text-muted dark:text-muted-dark">아직 올린 글이 없습니다.</p>')
    foot = (f'<footer class="border-t border-rule dark:border-rule-dark py-10 '
            f'text-xs text-muted dark:text-muted-dark tabular-nums">'
            f'갱신 {date.today()}</footer>')
    INDEX.write_text(HEAD + hero(total, rounds) + body + foot + FOOT, encoding="utf-8")
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
