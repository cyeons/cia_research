"""주간 컴퓨터교육/AI교육 논문 브리핑.

판별은 숫자로, 설명만 LLM이 한다.
  - 최신 트렌드 = 이번 주 토픽 빈도 / 지난 1년 평균 주간 빈도 (lift)
  - 이론적 배경 = 신규 논문들이 공통으로 인용한 문헌 (co-citation 빈도)
"""
import json, os, re, smtplib, sys, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, timedelta
from email.message import EmailMessage

MAIL_TO = os.environ.get("MAIL_TO", "")
WEEK_AGO = (date.today() - timedelta(days=7)).isoformat()
YEAR_AGO = (date.today() - timedelta(days=365)).isoformat()

TOPIC = ('("computational thinking" OR "programming education" OR "coding education" '
         'OR "AI literacy" OR "AI education" OR "artificial intelligence education" '
         'OR "block-based programming" OR "computer science education" OR "educational robotics")')
LEVEL = '(elementary OR primary OR "K-12" OR children OR "young learners")'
SEARCH = f"{TOPIC} AND {LEVEL}"


def oa(**params):
    """OpenAlex GET. mailto는 polite pool 진입용(무료, 키 불필요)."""
    if MAIL_TO:
        params["mailto"] = MAIL_TO   # polite pool (선택). 없어도 동작은 한다.
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def unabstract(inv):
    """OpenAlex는 초록을 역색인으로 준다. 위치→단어로 복원."""
    if not inv:
        return ""
    words = sorted((pos, w) for w, ps in inv.items() for pos in ps)
    return " ".join(w for _, w in words)[:2200]


def trending(n=12):
    """lift = 이번 주 빈도 / 1년 평균 주간 빈도. 절대 빈도로는 매주 같은 게 1등이라 쓸모없다.

    ponytail: OpenAlex group_by는 상위 200개만 준다. 1년치 목록에 없는 항목은
    '희귀'가 아니라 '측정 안 됨'이므로 lift를 계산하지 않고 버린다. 200위 밖까지
    보려면 주별 카운트를 직접 누적해야 하는데, 그 상태 파일값이 아직 없다.
    """
    def counts(since, key):
        g = oa(filter=f"from_publication_date:{since},title_and_abstract.search:{SEARCH}",
               group_by=key)["group_by"]
        return {x["key_display_name"]: x["count"] for x in g}

    out = []
    for key in ("topics.id", "keywords.id"):
        week, year = counts(WEEK_AGO, key), counts(YEAR_AGO, key)
        for name, c in week.items():
            base = year.get(name, 0)
            if c < 3 or base < 10:     # 소표본 lift는 요동친다 / 베이스라인 없으면 판단 보류
                continue
            out.append({"name": name, "week": c, "year": base,
                        "lift": round(c / (base / 52), 1)})
    out.sort(key=lambda x: -x["lift"])
    return out[:n]


def links_for(w):
    """PDF 직링크 > OA 랜딩페이지 > DOI. 이 분야는 OA 비율이 ~84%라 대부분 바로 열린다."""
    b = w.get("best_oa_location") or {}
    is_oa = (w.get("open_access") or {}).get("is_oa", False)
    return {"pdf": b.get("pdf_url"),
            "full_text": b.get("landing_page_url") if is_oa else None,
            "doi": w.get("doi"),
            "paywalled": not is_oa}


def new_papers(n=50):
    fields = ("id,doi,title,publication_year,cited_by_count,referenced_works,"
              "abstract_inverted_index,primary_location,open_access,best_oa_location")
    r = oa(filter=f"from_publication_date:{WEEK_AGO},title_and_abstract.search:{SEARCH}",
           select=fields, per_page=n, sort="cited_by_count:desc")
    for w in r["results"]:
        loc = w.get("primary_location") or {}
        w["venue"] = ((loc.get("source") or {}).get("display_name")) or ""
        w["abstract"] = unabstract(w.pop("abstract_inverted_index", None))
        w["links"] = links_for(w)
    return r["results"]


def foundations(papers, n=10):
    """여러 신규 논문이 '공통으로' 인용한 문헌 = 이 분야의 이론적 토대."""
    freq = Counter(ref for p in papers for ref in (p.get("referenced_works") or []))
    top = [(rid, c) for rid, c in freq.most_common(40) if c >= 2][:n]
    if not top:
        return []
    ids = "|".join(rid.rsplit("/", 1)[-1] for rid, _ in top)
    meta = {w["id"]: w for w in oa(filter=f"openalex_id:{ids}",
                                   select="id,title,publication_year,cited_by_count,doi",
                                   per_page=len(top))["results"]}
    return [{**meta[rid], "co_cited_by": c} for rid, c in top if rid in meta]


def kci(n=30):
    """국내 등재지. KCI OpenAPI는 XML이고 스키마 문서가 얕아서 태그명을 추정하지 않고 훑는다."""
    key = os.environ.get("KCI_KEY")
    if not key:
        return []
    url = "https://open.kci.go.kr/po/openapi/openApiSearch.kci?" + urllib.parse.urlencode(
        {"apiCode": "articleSearch", "key": key, "title": "컴퓨팅사고력|인공지능교육|소프트웨어교육|정보교육",
         "displayCount": n, "page": 1})
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            root = ET.fromstring(r.read())
    except Exception as e:
        print(f"[warn] KCI 실패: {e}", file=sys.stderr)
        return []

    def pick(rec, *names):
        for el in rec.iter():
            if el.tag.split("}")[-1] in names and (el.text or "").strip():
                return el.text.strip()
        return ""

    recs = [e for e in root.iter() if e.tag.split("}")[-1] in ("record", "article", "item", "output")]
    if not recs:
        print(f"[warn] KCI 레코드 없음. 루트 하위 태그: {[c.tag for c in root][:10]}", file=sys.stderr)
    out = []
    for rec in recs[:n]:
        t = pick(rec, "title", "articleTitle", "article-title", "titleKor")
        if t:
            out.append({"title": t,
                        "journal": pick(rec, "journalName", "journal-title", "journalTitle"),
                        "year": pick(rec, "pubYear", "pubYearInfo", "year"),
                        "url": pick(rec, "url", "articleUrl", "link")})
    return out


def summarize(trends, papers, founds, domestic):
    data = {
        "이번주_급상승_토픽(lift=평소대비배수)": trends,
        "신규논문_해외": [{k: p[k] for k in ("title", "venue", "publication_year", "cited_by_count", "abstract", "links")}
                     for p in papers[:25]],
        "신규논문_국내_KCI": domestic,
        "공통인용_문헌(이론적배경_후보)": founds,
    }
    system = (
        "너는 초등 컴퓨터교육/AI교육을 연구하는 대학원생의 주간 리서치 어시스턴트다. "
        "순위와 수치는 이미 통계로 확정되어 전달된다. 재정렬하거나 새로 판단하지 말고, "
        "주어진 숫자가 무엇을 뜻하는지 해석하고 맥락을 붙여라. "
        "데이터에 없는 논문을 언급하지 마라. 확실하지 않으면 '자료 부족'이라고 써라. "
        "링크는 반드시 links 객체에 있는 URL만 <a href>로 걸어라. URL을 지어내지 마라. "
        "우선순위는 pdf > full_text > doi이고, paywalled가 true면 제목 뒤에 '(유료·도서관 프록시 필요)'를 붙여라. "
        "출력은 이메일 본문용 HTML 조각(<h2>/<p>/<ul>/<table>, 인라인 style 최소)만. "
        "<html>/<body> 태그와 마크다운 코드펜스는 쓰지 마라."
    )
    prompt = f"""아래 JSON으로 주간 브리핑을 작성해라. 한국어. 4개 섹션:

1. <h2>이번 주 흐름</h2> — 급상승 토픽 중 실제로 의미 있는 3~4개만. lift가 높아도 우연일 수 있으면 그렇게 써라. 각 토픽이 왜 지금 뜨는지 신규논문 초록에서 근거를 찾아 연결.
2. <h2>읽을 만한 신규 논문 5편</h2> — 초등/K-12 현장 적합성과 방법론 견고함 기준. 편당 아래 3줄 구조를 지켜라:
   - <b>제목</b>(링크) — 저널, 연도. 열람 링크를 PDF/본문/DOI 순으로 붙여라.
   - <b>쉽게 말하면</b>: 전문용어 없이 2문장. "~를 알아보려고 ~명에게 ~를 시켜봤더니 ~였다" 형태. 통계 용어는 "차이가 꽤 컸다" 식으로 풀어라. 이건 정독용이 아니라 <i>어느 걸 읽을지 고르기 위한</i> 요약이다.
   - <b>연구적 의미</b>: 학술 용어를 써도 된다. 표본·설계의 한계나 선행연구와의 관계를 1~2문장.
3. <h2>이론적 배경 후보</h2> — 공통인용 문헌 표(문헌 / 연도 / 이번 주 공동인용 수 / 어떤 이론적 역할). 여러 신규 논문이 동시에 인용했다는 건 그게 이 분야의 공통 전제라는 뜻임을 짚어줘라.
4. <h2>국내 동향</h2> — KCI 결과가 있으면 해외와의 관심사 차이를, 비었으면 "이번 주 신규 없음"만.

<data>
{json.dumps(data, ensure_ascii=False)}
</data>"""
    return gemini(system, prompt)


GEMINI_MODEL = "gemini-3.8-flash"


def gemini(system, prompt):
    """generateContent REST 직접 호출. SDK를 안 쓰니 의존성이 0이 된다."""
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 16000, "temperature": 0.3},
    }).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        data=body,
        headers={"content-type": "application/json",
                 "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Gemini 호출 실패 {e.code}: {e.read().decode('utf-8', 'replace')[:800]}")

    cands = out.get("candidates") or []
    if not cands:
        sys.exit(f"Gemini가 후보를 반환하지 않았습니다: {json.dumps(out, ensure_ascii=False)[:800]}")
    text = "".join(p.get("text", "") for p in cands[0]["content"]["parts"])
    if not text.strip():
        sys.exit(f"Gemini 응답이 비었습니다 (finishReason={cands[0].get('finishReason')})")
    # 모델이 ```html 펜스를 붙이는 경우가 있다.
    return re.sub(r"^\s*```(?:html)?\s*|\s*```\s*$", "", text)


PRINT_CSS = """
  body{font-family:-apple-system,'Malgun Gothic',sans-serif;line-height:1.65;
       max-width:760px;margin:0 auto;padding:24px;color:#1a1a1a}
  h2{margin-top:2em;padding-bottom:.3em;border-bottom:2px solid #eee}
  table{border-collapse:collapse;width:100%}
  td,th{border:1px solid #ddd;padding:6px 10px;text-align:left}
  a{color:#0645ad}
  /* 브라우저 Ctrl+P -> PDF 저장용. 논문 항목이 페이지 경계에서 잘리지 않게. */
  @page{margin:2cm}
  @media print{a{color:#000}li,tr{break-inside:avoid}h2{break-after:avoid}}
"""


def render(fragment, archive_url=None):
    """조각 -> 독립 HTML 문서. 메일 본문과 아카이브 파일이 같은 걸 쓴다."""
    back = f'<p style="font-size:.9em"><a href="{archive_url}">웹에서 보기 / PDF로 저장</a></p>' if archive_url else ""
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>논문 브리핑 {date.today()}</title><style>{PRINT_CSS}</style></head>'
            f'<body><h1>컴퓨터교육·AI교육 주간 브리핑</h1>'
            f'<p style="color:#666">{date.today()}</p>{back}{fragment}</body></html>')


def archive(doc):
    """docs/ 에 주차별로 쌓고 목차를 다시 만든다. GitHub Pages가 그대로 서빙한다."""
    os.makedirs("docs", exist_ok=True)
    with open(f"docs/{date.today()}.html", "w", encoding="utf-8") as f:
        f.write(doc)
    weeks = sorted((n for n in os.listdir("docs") if n[0].isdigit()), reverse=True)
    items = "".join(f'<li><a href="{n}">{n[:-5]}</a></li>' for n in weeks)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
                f'<title>논문 브리핑 아카이브</title><style>{PRINT_CSS}</style></head>'
                f'<body><h1>주간 브리핑 아카이브</h1><ul>{items}</ul></body></html>')


def pages_url():
    """웹 아카이브 링크. 기본은 끔.

    GitHub Pages는 저장소가 비공개여도 사이트를 인터넷에 공개한다. 자동으로 켜지 않는다.
    쓰려면 Pages를 직접 켠 뒤 PAGES_URL 시크릿에 사이트 주소를 넣어라.
    끄더라도 docs/ 에는 계속 쌓이므로 git pull 받아 로컬에서 열면 된다.
    """
    base = os.environ.get("PAGES_URL", "").rstrip("/")
    return f"{base}/{date.today()}.html" if base else None


def send(doc):
    m = EmailMessage()
    m["Subject"] = f"[주간] 컴퓨터교육·AI교육 논문 브리핑 {date.today()}"
    m["From"] = m["To"] = os.environ["MAIL_TO"]
    m.set_content("HTML 메일입니다.")
    m.add_alternative(doc, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(os.environ["MAIL_TO"], os.environ["GMAIL_APP_PW"])
        s.send_message(m)


def main():
    trends = trending()
    papers = new_papers()
    print(f"토픽 {len(trends)} / 신규논문 {len(papers)}", file=sys.stderr)
    doc = render(summarize(trends, papers, foundations(papers), kci()), pages_url())
    archive(doc)
    print(f"docs/{date.today()}.html 저장", file=sys.stderr)
    if "--dry-run" not in sys.argv:
        send(doc)


if __name__ == "__main__":
    main()
