"""AI·디지털 교육의 이론들을 하나씩 ELI5로 정리한다.

    python theories.py            # 이론 목록을 뽑고, 아직 없는 것만 만든다
    python theories.py TPACK      # 이름에 이게 들어간 이론만 (다시) 만든다
    python theories.py --force    # 전부 다시 만든다

한 장에 여러 이론을 몰아넣으면 ELI5가 잘하는 걸 못 한다 — 개념 하나를 그림으로
풀어내는 게 이 형식의 값어치다. 그래서 이론마다 페이지를 따로 만들고, 목차만 한 장 둔다.

어떤 이론을 다룰지는 데이터가 정한다. 표본 논문 수백 편의 참고문헌을 집계해
공통으로 딛고 선 문헌을 찾고(backbone), 그것들이 어떤 이론으로 묶이는지 판별한다.
내가 아는 이론을 늘어놓는 게 아니다.

eli5.py와 같은 로컬 Claude Code(구독)를 쓰므로 API 키가 필요 없다.
"""
import json, os, re, sys, webbrowser
from collections import Counter
from pathlib import Path

import weekly
from eli5 import DESIGN, DIAGRAMS, RULES, run_claude, split_title

OUT_DIR = Path("docs/theories")
INDEX = Path("docs/theories.html")
SAMPLE_PER_THEME = 60          # 갈래당 표본. 180편이면 backbone이 안정적으로 잡힌다.
MIN_CO_CITED = 4               # 4편 미만이 인용한 문헌은 backbone이 아니라 그냥 참고문헌
SINCE = "2023-01-01"


def name_slug(name):
    """이론 이름 -> 파일명. eli5.slug()는 URL·경로용이라 '/'를 경로 구분자로 보고
    뒷부분만 취한다 — 'Constructionist / learning-by-design'이 통째로 잘렸다."""
    return re.sub(r"[^\w.-]+", "_", name, flags=re.UNICODE).strip("_")[:70]


def backbone(top_n=25):
    """여러 논문이 공통으로 인용한 문헌 = 이 분야의 이론적 토대."""
    sample = []
    for theme, topic in weekly.THEMES.items():
        q = f"{topic} AND {weekly.LEVEL} AND {weekly.CONTEXT} {weekly.EXCLUDE}"
        try:
            sample += weekly.oa(
                filter=f"from_publication_date:{SINCE},title_and_abstract.search:{q}",
                select="id,referenced_works", per_page=SAMPLE_PER_THEME,
                sort="relevance_score:desc")["results"]
        except Exception as e:
            print(f"[warn] 표본 수집 실패({theme}): {e}", file=sys.stderr)
    print(f"표본 {len(sample)}편의 참고문헌 집계 중...", file=sys.stderr)

    freq = Counter(r for p in sample for r in (p.get("referenced_works") or []))
    top = [(rid, c) for rid, c in freq.most_common(top_n * 2) if c >= MIN_CO_CITED][:top_n]
    if not top:
        sys.exit("공동인용 문헌을 찾지 못했습니다. 검색어나 기간을 확인하세요.")

    ids = "|".join(rid.rsplit("/", 1)[-1] for rid, _ in top)
    meta = {w["id"]: w for w in weekly.oa(
        filter=f"openalex_id:{ids}",
        select="id,title,publication_year,cited_by_count,doi,open_access,best_oa_location",
        per_page=len(top))["results"]}
    return [{"title": meta[r]["title"], "year": meta[r]["publication_year"],
             "cited_total": meta[r]["cited_by_count"], "co_cited_here": c,
             "links": weekly.links_for(meta[r])}
            for r, c in top if r in meta], len(sample)


IDENTIFY = """아래는 초등 AI·디지털 교육 논문 표본이 공통으로 인용한 문헌 목록이다.
co_cited_here가 클수록 이 분야의 공통 전제다.

이 문헌들이 어떤 <b>이름 붙은 이론·프레임워크</b>로 묶이는지 판별해라.

규칙:
- 목록에 근거가 없는 이론은 만들지 마라. 네가 아는 유명한 이론이라도 여기 문헌이
  뒷받침하지 않으면 넣지 마라.
- 한 이론에 문헌이 2편 미만이면 넣지 마라 — 지도가 아니라 추측이 된다.
- 3~6개. 많이 쪼개지 말고, 초등 교사·대학원생이 구분해서 쓸 만한 단위로 묶어라.

출력은 JSON 배열 하나만. 설명이나 코드펜스를 붙이지 마라.
[{"name": "한국어 이론 이름(영문 병기 가능)",
  "one_line": "무엇을 설명하는 이론인지 한 문장",
  "source_titles": ["뒷받침하는 문헌 제목 그대로", "..."]}]"""

SECTIONS = """이 이론 하나만 다룬다. 다른 이론은 비교할 때만 언급해라.

<h2>그림으로 보는 핵심</h2>
이 문서의 主다. 그림 3~5개. 그림마다 아래 1~2문장만.
이 섹션만 보고도 이 이론이 무슨 말인지 알아야 한다.

<h2>한 문장으로</h2>
<div class="callout">이 이론이 말하는 것 한 줄.</div>

<h2>무엇을 설명하려는 이론인가</h2>
이 이론이 답하려는 질문이 무엇인지. 전문용어 없이. 일상 비유를 하나 써라.
이 이론이 나오기 전에는 무엇을 설명하지 못했는지 짚으면 좋다.

<h2>어디서 나왔나</h2>
누가 언제, 어떤 문제 때문에 내놓았는지 3~5문장. 근거 문헌을 링크로 짚어라.
데이터에 없는 연도·인물을 지어내지 마라. 모르면 '자료에 없음'이라고 써라.

<h2>초등 교실에서는</h2>
<b>이 문서에서 가장 중요한 섹션이다.</b> 이 이론이 수업 설계·생활지도에 실제로
무엇을 말해주는지 2~4개. 각 항목은 "~할 때 ~하게 하라" 수준으로 구체적으로.
"중요하다", "고려해야 한다" 같은 말로 끝내지 마라.

<h2>이 이론으로 연구한다면</h2>
이 이론을 이론적 배경으로 삼는다면 어떤 연구 질문이 자연스러운지 2~3개.
각 질문마다 어느 문헌을 딛고 서야 하는지 링크로.

<h2>조심할 점</h2>
이 이론의 한계, 또는 이 분야에서 이 이론이 오용되는 방식. 2~3개.

<h2>근거 문헌</h2>
<ul>로. 제목(링크) — 연도, 이 표본에서 공동인용 N편. 각 한 줄로 어떤 역할인지."""


def identify(bb):
    raw = run_claude(f"{IDENTIFY}\n\n<data>\n{json.dumps(bb, ensure_ascii=False)}\n</data>")
    raw = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw).strip()
    try:
        return json.loads(raw[raw.index("["):raw.rindex("]") + 1])
    except (ValueError, json.JSONDecodeError) as e:
        sys.exit(f"이론 목록을 파싱하지 못했습니다: {e}\n받은 것: {raw[:400]}")


def explain(theory, bb):
    """이론 하나를 ELI5 한 장으로."""
    titles = set(theory.get("source_titles") or [])
    sources = [b for b in bb if b["title"] in titles] or bb[:6]
    prompt = "\n\n".join([
        DESIGN, RULES, DIAGRAMS,
        f'다룰 이론: <b>{theory["name"]}</b> — {theory.get("one_line", "")}',
        SECTIONS,
        f"<data>\n{json.dumps(sources, ensure_ascii=False)}\n</data>"])
    title, fragment = split_title(run_claude(prompt), theory["name"])
    return title, weekly.render(fragment, title=title)


def write_index(entries):
    items = "".join(
        f'<li><a href="theories/{f}">{t}</a> — {o}</li>' for t, o, f in entries)
    INDEX.write_text(weekly.render(
        f'<p style="font-size:.9em">표본 논문의 공동인용에서 추려낸 이론들. '
        f'각 항목이 한 장짜리 설명으로 이어집니다. · {weekly.date.today()}</p>'
        f"<h2>이론 목록</h2><ul>{items}</ul>",
        title="AI·디지털 교육 이론 모음"), encoding="utf-8")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    bb, n_sample = backbone()
    print(f"backbone {len(bb)}건 — 이론 판별 중...", file=sys.stderr)
    theories = identify(bb)
    print(f"이론 {len(theories)}개: {', '.join(t['name'] for t in theories)}", file=sys.stderr)

    entries = []
    for t in theories:
        fname = f"{name_slug(t['name'])}.html"
        path = OUT_DIR / fname
        wanted = not args or any(a.lower() in t["name"].lower() for a in args)
        if wanted and (force or not path.exists()):
            print(f"  만드는 중: {t['name']}", file=sys.stderr)
            title, doc = explain(t, bb)
            path.write_text(doc, encoding="utf-8")
        elif path.exists():
            print(f"  건너뜀(이미 있음): {t['name']}", file=sys.stderr)
        if path.exists():
            entries.append((t["name"], t.get("one_line", ""), fname))

    write_index(entries)
    print(f"저장: {INDEX} (+ {len(entries)}장)", file=sys.stderr)
    if "--no-open" not in sys.argv:
        webbrowser.open(INDEX.resolve().as_uri())


if __name__ == "__main__":
    main()
