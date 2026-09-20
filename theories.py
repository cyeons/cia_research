"""AI·디지털 교육의 이론 지도를 만든다.

    python theories.py

주간 브리핑은 매주 이론 문헌을 한두 편씩 흘려보낸다. 그걸로는 지도가 안 그려진다.
이 도구는 반대로 간다 — 한 번에 수백 편의 참고문헌을 집계해서, 이 분야가 실제로
'공통으로 딛고 선' 문헌을 찾아내고 그것들이 어떤 이론으로 묶이는지 정리한다.

근거는 두 가지다:
  1) 공동인용 — 논문 180편의 참고문헌을 세면 backbone이 드러난다
     (실측: Long & Magerko 2020이 26편, Touretzky 2019가 21편에서 인용됨)
  2) 이론틀 논문 — 제목·초록에서 이론을 명시적으로 다루는 논문

수시로 돌릴 것이 아니다. 분기에 한 번쯤, 또는 이론 정리가 필요할 때 돌린다.
eli5.py와 같은 로컬 Claude Code(구독)를 쓰므로 API 키가 필요 없다.
"""
import os, sys, webbrowser
from collections import Counter
from pathlib import Path

import weekly
from eli5 import DESIGN, DIAGRAMS, run_claude, split_title

OUT = Path("docs/theories.html")
SAMPLE_PER_THEME = 60          # 갈래당 표본. 180편이면 backbone이 안정적으로 잡힌다.
MIN_CO_CITED = 4               # 4편 미만이 인용한 문헌은 backbone이 아니라 그냥 참고문헌
SINCE = "2023-01-01"           # 이론 지도라 최신성보다 축적이 중요하다


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


def theory_papers(n=12):
    """이론틀을 명시적으로 다루는 논문 — 이름 붙은 이론을 확인하는 용도."""
    q = ('("theoretical framework" OR "conceptual framework" OR "theoretical foundation" '
         'OR TPACK OR "technology acceptance" OR UTAUT OR SAMR OR constructionism '
         'OR "self-determination theory" OR "cognitive load" OR "situated learning")')
    full = f'{q} AND {weekly.THEMES["수업"]} AND {weekly.LEVEL} {weekly.EXCLUDE}'
    try:
        r = weekly.oa(filter=f"from_publication_date:{SINCE},title_and_abstract.search:{full}",
                      select="title,publication_year,cited_by_count,abstract_inverted_index,doi,"
                             "open_access,best_oa_location",
                      per_page=n, sort="relevance_score:desc")["results"]
    except Exception as e:
        print(f"[warn] 이론틀 논문 수집 실패: {e}", file=sys.stderr)
        return []
    return [{"title": w["title"], "year": w["publication_year"],
             "cited_total": w["cited_by_count"],
             "abstract": weekly.unabstract(w.pop("abstract_inverted_index", None))[:900],
             "links": weekly.links_for(w)} for w in r]


TASK = """초등 컴퓨터교육·AI교육을 공부하는 대학원생을 위한 <b>이론 지도</b>를 만든다.
개별 논문 요약이 아니다. 이 분야가 어떤 이론 위에 서 있는지 <b>한 장으로 보이게</b> 하는 게 목적이다.

아래 데이터는 통계로 확정된 것이다:
- <b>backbone</b>: 표본 논문들이 공통으로 인용한 문헌. co_cited_here가 클수록 이 분야의 공통 전제다.
- <b>theory_papers</b>: 이론틀을 명시적으로 다루는 논문.

데이터에 없는 문헌을 지어내지 마라. 네가 아는 이론이라도 이 목록에 근거가 없으면 쓰지 마라.
다만 목록의 문헌이 어떤 <i>이름 붙은 이론</i>에 해당하는지(예: 구성주의, 자기결정성이론,
기술수용모형)는 제목·초록에서 읽히는 범위에서 밝혀도 된다. 확실하지 않으면 그렇게 표시해라.

<h2>한눈에 보는 지도</h2>
이 문서의 主다. 그림으로 이론 지형을 보여줘라. 최소 3개:
- <b>계보</b>: 오래된 토대에서 최근 틀로 이어지는 흐름. 연도를 축으로.
- <b>갈래</b>: 이론들이 무엇을 설명하려 하는지로 묶기(무엇을 가르칠까 / 어떻게 배우나 /
  왜 받아들이나 / 무엇을 조심하나 등, 데이터에서 실제로 읽히는 묶음으로).
- <b>어디가 비어 있나</b>: 인용이 몰린 곳과 얇은 곳의 대비.
그림마다 아래 1~2문장.

<h2>이 분야가 딛고 선 문헌</h2>
<table>로: 문헌(링크) / 연도 / 여기서 공동인용 / 전체 인용 / 어떤 역할인지 한 줄.
co_cited_here 순으로. 최대 12행.

<h2>이름 붙은 이론들</h2>
데이터에서 확인되는 이론을 3~6개. 각각 <h3>로:
- 무엇을 설명하는 이론인가 (전문용어 없이 3문장 이내)
- 이 분야에서 어떤 자리를 차지하나 — 근거가 되는 문헌을 링크로 짚어라
- <b>초등 교실에서는</b>: 이 이론이 수업 설계에 실제로 무엇을 말해주는가. 구체적으로.

<h2>연구 계획에 쓸 때</h2>
이론적 배경 절을 쓴다면 어느 문헌을 어떤 순서로 딛는 게 자연스러운지 2~3개 경로로 제안해라.
각 경로마다 "이 조합은 어떤 연구 질문에 맞는지" 한 줄.

<h2>한계</h2>
이 지도가 무엇을 못 보는지. 표본 편향(영어권·OpenAlex 색인·최근 연도 가중)을 밝혀라."""


def main():
    bb, n_sample = backbone()
    tp = theory_papers()
    print(f"backbone {len(bb)}건 / 이론틀 논문 {len(tp)}건", file=sys.stderr)

    import json
    data = json.dumps({"backbone": bb, "theory_papers": tp,
                       "표본_논문_수": n_sample}, ensure_ascii=False)
    prompt = "\n\n".join([
        DESIGN, DIAGRAMS, TASK,
        "첫 줄은 <!--TITLE: 짧은 한국어 제목--> 주석이다. HTML 조각만 출력해라.",
        f"<data>\n{data}\n</data>"])

    title, fragment = split_title(run_claude(prompt), "AI·디지털 교육 이론 지도")
    doc = weekly.render(
        f'<p style="font-size:.9em">표본 {n_sample}편의 참고문헌 집계 · {weekly.date.today()}</p>{fragment}',
        title=title)
    os.makedirs("docs", exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    print(f"저장: {OUT}", file=sys.stderr)
    if "--no-open" not in sys.argv:
        webbrowser.open(OUT.resolve().as_uri())


if __name__ == "__main__":
    main()
