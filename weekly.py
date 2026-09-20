"""주간 컴퓨터교육/AI교육 논문 브리핑.

판별은 숫자로, 설명만 LLM이 한다.
  - 최신 트렌드 = 이번 주 토픽 빈도 / 지난 1년 평균 주간 빈도 (lift)
  - 이론적 배경 = 신규 논문들이 공통으로 인용한 문헌 (co-citation 빈도)
"""
import json, os, re, smtplib, sys, time, urllib.error, urllib.parse, urllib.request
from collections import Counter
from datetime import date, timedelta
from email.message import EmailMessage

MAIL_TO = os.environ.get("MAIL_TO", "")
WEEK_AGO = (date.today() - timedelta(days=7)).isoformat()
YEAR_AGO = (date.today() - timedelta(days=365)).isoformat()

# 검색 기준: 최신성이 아니라 정확성. 정확하다 = 초등학교 교사가 읽고 수업·생활지도에
# 옮길 거리가 있다. 세 조건을 모두 만족해야 한다(AND):
#   TOPIC   무엇을 다루나 — AI/디지털 수업, AI 윤리, 디지털 과몰입
#   LEVEL   누구를 다루나 — 초등·K-12 (대학·성인 제외)
#   CONTEXT 어떤 관점인가 — 교실·수업·교사 (이게 없으면 같은 주제라도 보건 연구가 온다:
#           과몰입 검색 상위가 비만·충치·자세였다. 교사에게 시사점이 없다.)
TOPIC = ('("computational thinking" OR "programming education" OR "coding education" '
         'OR "AI literacy" OR "AI education" OR "artificial intelligence education" '
         'OR "generative AI" OR "computer science education" OR "educational robotics" '
         'OR "AI ethics" OR "algorithmic bias" OR "digital citizenship" '
         'OR "screen time" OR "digital addiction" OR "smartphone addiction" '
         'OR "problematic internet use" OR "digital wellbeing")')
LEVEL = ('(elementary OR "primary school" OR "primary education" OR "K-12" '
         'OR schoolchildren OR pupils)')
CONTEXT = ('(classroom OR teaching OR curriculum OR instruction OR teacher '
           'OR "learning outcomes" OR pedagogy OR school)')
EXCLUDE = ('NOT (undergraduate OR university OR "higher education" OR medical OR nursing '
           'OR obesity OR dental OR myopia OR posture OR sleep OR psychiatric)')
SEARCH = f"{TOPIC} AND {LEVEL} AND {CONTEXT} {EXCLUDE}"


def oa(**params):
    """OpenAlex GET. mailto는 polite pool 진입용(무료, 키 불필요).

    429 재시도가 필요하다: 한 번 돌 때 OpenAlex를 7번 부르는데(trending 4 +
    papers + foundations + reviews), GitHub Actions 러너는 IP를 다른 사용자와
    공유해서 polite pool에 있어도 429가 난다. 실제로 리뷰 호출 하나 때문에
    브리핑 전체가 죽은 적이 있다.
    """
    if MAIL_TO:
        params["mailto"] = MAIL_TO   # polite pool (선택). 없어도 동작은 한다.
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 3:
                raise
            wait = 5 * 2 ** attempt          # 5, 10, 20초
            print(f"[warn] OpenAlex 429 — {wait}초 후 재시도", file=sys.stderr)
            time.sleep(wait)


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


# 정확도 우선이므로 1주가 아니라 1년치에서 고른다. 대신 매주 같은 상위 논문이
# 반복되므로, 한 번 보낸 것은 기억해 두고 다음부터 건너뛴다.
PAPER_WINDOW_DAYS = 365
SEEN_PAPERS_PATH = "docs/seen_papers.json"
SEEN_KEEP = 300                  # 이 이상은 버린다. 1년 창에 후보가 2천 건대라 충분하다.


def _load_seen():
    try:
        with open(SEEN_PAPERS_PATH, encoding="utf-8") as f:
            return json.load(f).get("ids", [])
    except (OSError, ValueError):
        return []


def papers(n=25):
    """정확도 순으로 n편. 이미 보낸 것은 뺀다."""
    fields = ("id,doi,title,publication_year,cited_by_count,referenced_works,"
              "abstract_inverted_index,primary_location,open_access,best_oa_location")
    since = (date.today() - timedelta(days=PAPER_WINDOW_DAYS)).isoformat()
    # 중복 제거로 빠지는 만큼 넉넉히 받는다.
    r = oa(filter=f"from_publication_date:{since},title_and_abstract.search:{SEARCH}",
           select=fields, per_page=n * 3, sort="relevance_score:desc")

    seen = set(_load_seen())
    out = []
    for w in r["results"]:
        if w["id"] in seen:
            continue
        loc = w.get("primary_location") or {}
        w["venue"] = ((loc.get("source") or {}).get("display_name")) or ""
        w["abstract"] = unabstract(w.pop("abstract_inverted_index", None))
        w["links"] = links_for(w)
        out.append(w)
        if len(out) >= n:
            break

    if not out:      # 1년치를 다 돌았다. 기억을 비우고 처음부터.
        print("[warn] 후보가 모두 소진됐다 — seen 목록을 비운다", file=sys.stderr)
        os.makedirs("docs", exist_ok=True)
        with open(SEEN_PAPERS_PATH, "w", encoding="utf-8") as f:
            json.dump({"ids": []}, f)
        return papers(n)

    # 병합을 먼저 끝낸다. open(...,"w")는 여는 순간 파일을 비우므로,
    # 그 안에서 _load_seen()을 부르면 빈 파일을 읽어 기억이 매주 리셋된다.
    merged = (list(seen) + [w["id"] for w in out])[-SEEN_KEEP:]
    os.makedirs("docs", exist_ok=True)
    with open(SEEN_PAPERS_PATH, "w", encoding="utf-8") as f:
        json.dump({"ids": merged}, f)
    return out


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


# 1차 연구(단일 실험, 척도 타당화)만 모으면 브리핑이 지엽적이 된다 — EFA/Likert 같은
# 통계 기법명이 "급상승"으로 잡히는 게 그 증상이다. 체계적 문헌고찰 한 편은 논문
# 50~200편을 정리한 것이라, 같은 학술 자료인데도 층위가 다르다.
REVIEW_WINDOW_DAYS = 30   # 리뷰는 속보성이 아니다. 7일 창이면 2건뿐이라 대부분 빈다.


def reviews(n=5):
    try:
        return _reviews(n)
    except Exception as e:                # 보조 섹션이다. 죽어도 브리핑은 나가야 한다.
        print(f"[warn] 리뷰 수집 실패: {e}", file=sys.stderr)
        return []


def _reviews(n):
    since = (date.today() - timedelta(days=REVIEW_WINDOW_DAYS)).isoformat()
    fields = ("title,publication_year,cited_by_count,abstract_inverted_index,"
              "primary_location,open_access,best_oa_location,doi")
    # 30일 창에서는 인용수가 전부 0이라 인용순 정렬이 무의미하다. 최신순으로 받고,
    # 그중 어느 걸 실을지는 Gemini가 저널 평판까지 보고 고른다(약탈적 학술지가 섞인다).
    r = oa(filter=f"from_publication_date:{since},title_and_abstract.search:{SEARCH},type:review",
           select=fields, per_page=n * 2, sort="publication_date:desc")
    out = []
    for w in r["results"]:
        loc = w.get("primary_location") or {}
        out.append({"title": w["title"],
                    "venue": ((loc.get("source") or {}).get("display_name")) or "",
                    "year": w.get("publication_year"),
                    "cited_by_count": w.get("cited_by_count"),
                    "abstract": unabstract(w.pop("abstract_inverted_index", None)),
                    "links": links_for(w)})
    return out


# 국내 논문: KCI는 API 키 발급에 "접속 서버 IP"를 요구한다(고정 IP 필수).
# GitHub Actions 공유 러너는 실행마다 IP가 바뀌므로 원천적으로 안 맞는다.
# 대신 Crossref를 쓴다 — 키도 IP 등록도 없다. 목표 학회들이 DOI를 Crossref에
# 등록해 두고 있어서(한국인공지능교육학회, 한국정보교육학회, 한국컴퓨터교육학회,
# 한국실과교육연구학회) 커버리지도 충분하다. 다만 초록은 안 온다(제목·저자·DOI만).
DOMESTIC_JOURNALS = {
    "10.52618": "한국인공지능교육학회",
    "10.14352": "한국정보교육학회",
    "10.32431": "한국컴퓨터교육학회",
    "10.29113": "한국실과교육연구학회",
}
DOMESTIC_WINDOW_DAYS = 30   # 이 학회들은 계간지라 1주 기준이면 대부분 0건이 된다


def domestic(n=20):
    since = (date.today() - timedelta(days=DOMESTIC_WINDOW_DAYS)).isoformat()
    out = []
    for prefix, name in DOMESTIC_JOURNALS.items():
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
            {"filter": f"prefix:{prefix},from-pub-date:{since}",
             "rows": n, "sort": "published", "order": "desc",
             "mailto": MAIL_TO or "research@example.com"})  # polite pool, mailto 없어도 동작은 한다
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                items = json.load(r)["message"]["items"]
        except Exception as e:
            print(f"[warn] Crossref({name}) 실패: {e}", file=sys.stderr)
            continue
        for w in items:
            title_en = (w.get("title") or [""])[0]
            title_ko = (w.get("original-title") or [""])[0]
            out.append({"title": title_ko or title_en, "title_en": title_en if title_ko else "",
                        "journal": name, "year": (w.get("published") or {}).get("date-parts", [[None]])[0][0],
                        "url": f"https://doi.org/{w['DOI']}"})
    return out[:n]


# KERIS 「디지털교육 국내외 동향」 — 월간(통권 224호까지). 공개 API도 RSS도 없어서
# HTML을 긁는다. 검증된 3단계 체인이고 인증·세션이 필요 없다:
#   1) POST 목록 -> <table> 행마다 data-id(fileGrpKey)
#   2) GET fileDownChk.do?fileGrpKey -> JSON {fileKey, 파일명, 크기}
#   3) GET fileDownload.do?fileKey   -> PDF
# HTML 구조에 의존하므로 언제든 깨질 수 있다. 깨져도 브리핑 전체는 정상 발송되고
# 이 섹션만 빈다(stderr 경고는 Actions 로그에 남는다).
KERIS_BASE = "https://www.keris.or.kr"
KERIS_MI = "1143"                 # 디지털교육 국내외 동향 메뉴 id
KERIS_UA = {"User-Agent": "Mozilla/5.0"}
SEEN_PATH = "docs/keris_seen.json"   # 워크플로가 docs/ 를 커밋하므로 주간 상태가 유지된다


def keris_latest():
    """최신호 1건. 실패하면 None — 호출부에서 섹션만 비운다."""
    try:
        req = urllib.request.Request(
            f"{KERIS_BASE}/main/ad/pblcte/selectPblcteOVSEAList.do",
            data=f"mi={KERIS_MI}&pageIndex=1".encode(), headers=KERIS_UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"[warn] KERIS 목록 실패: {e}", file=sys.stderr)
        return None

    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        grp = re.search(r'data-id="(\d+)"', row)
        if not grp:
            continue
        text = " ".join(re.sub(r"<[^>]+>", " ", row).split())
        title = re.search(r"번호\s+\d+\s+(.*?)\s+담당자", text)
        if not title:
            continue
        issue = re.search(r"\[통권\s*(\d+)\s*호\]", text)
        info = _keris_file(grp.group(1))
        return {"title": title.group(1), "issue": int(issue.group(1)) if issue else None,
                **(info or {})}

    print(f"[warn] KERIS 목록 파싱 0건 — HTML 구조가 바뀌었을 수 있다", file=sys.stderr)
    return None


def _keris_file(file_grp_key):
    """fileGrpKey -> 실제 PDF 링크와 파일 정보."""
    try:
        req = urllib.request.Request(
            f"{KERIS_BASE}/main/ad/pblcte/fileDownChk.do?"
            + urllib.parse.urlencode({"fileGrpKey": file_grp_key}), headers=KERIS_UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            files = json.load(r).get("infoMediaFileList") or []
    except Exception as e:
        print(f"[warn] KERIS 파일정보 실패: {e}", file=sys.stderr)
        return None
    if not files:
        return None
    f = files[0]
    return {"filename": f.get("orignlFileNm", ""),
            "mb": round((f.get("fileSize") or 0) / 1024 / 1024, 1),
            "url": f"{KERIS_BASE}/common/fileDownload.do?"
                   + urllib.parse.urlencode({"fileKey": f["fileKey"], "dwlTy": "pblcte"})}


def keris_report():
    """최신호 + 지난주 대비 새 호인지. 월간이라 4주 중 3주는 is_new=False."""
    latest = keris_latest()
    if not latest:
        return None
    try:
        with open(SEEN_PATH, encoding="utf-8") as f:
            seen = json.load(f).get("issue")
    except (OSError, ValueError):
        seen = None
    latest["is_new"] = latest.get("issue") != seen
    os.makedirs("docs", exist_ok=True)
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump({"issue": latest.get("issue"), "checked": date.today().isoformat()}, f)
    return latest


def summarize(trends, papers, founds, domestic, revs, keris):
    data = {
        "이번주_급상승_토픽(lift=평소대비배수)": trends,
        "논문_해외(정확도순_최근1년)": [{k: p[k] for k in ("title", "venue", "publication_year", "cited_by_count", "abstract", "links")}
                     for p in papers[:25]],
        "신규논문_국내(최근30일_초록없음)": domestic,
        "공통인용_문헌(이론적배경_후보)": founds,
        "리뷰_메타분석(최근30일)": revs,
        "KERIS_디지털교육_국내외동향_최신호": keris,
    }
    system = (
        "너는 초등 컴퓨터교육/AI교육을 연구하는 대학원생의 주간 리서치 어시스턴트다. "
        "순위와 수치는 이미 통계로 확정되어 전달된다. 재정렬하거나 새로 판단하지 말고, "
        "주어진 숫자가 무엇을 뜻하는지 해석하고 맥락을 붙여라. "
        "데이터에 없는 논문을 언급하지 마라. 확실하지 않으면 '자료 부족'이라고 써라. "
        "모든 섹션에서 논문·문헌 제목은 실제 데이터에 있는 URL로 <a href> 링크를 걸어라 "
        "(해외 신규 논문과 리뷰는 links.pdf > links.full_text > links.doi 순, 이론적 배경·국내 동향·"
        "KERIS는 각각 doi 필드, url 필드, url 필드). 그래야 클릭해서 바로 읽거나 eli5 도구에 넣을 수 있다. "
        "URL을 지어내지 말고, 필드가 비어 있으면 링크 없이 텍스트만 써라. "
        "해외 신규 논문에서 paywalled가 true면 제목 뒤에 '(유료·도서관 프록시 필요)'를 붙여라. "
        "출력은 이메일 본문용 HTML 조각(<h2>/<p>/<ul>/<table>, 인라인 style 최소)만. "
        "<html>/<body> 태그와 마크다운 코드펜스는 쓰지 마라."
    )
    prompt = f"""아래 JSON으로 주간 브리핑을 작성해라. 한국어. 6개 섹션, 아래 순서 그대로:

1. <h2>이번 주 흐름</h2> — 급상승 토픽 중 실제로 의미 있는 3~4개만. lift가 높아도 우연일 수 있으면 그렇게 써라. 각 토픽이 왜 지금 뜨는지 신규논문 초록에서 근거를 찾아 연결. 주의: EFA·Likert·구조방정식 같은 <i>통계 기법 이름</i>은 설문 논문이면 어느 분야든 나오는 공통 어휘라, 급상승해도 이 분야의 연구 흐름이 아니라 "이번 주에 척도 개발 논문이 몰렸다"는 뜻일 뿐이다. 그렇게 보이면 그렇게 써라.
2. <h2>큰 그림 — 리뷰·메타분석</h2> — 체계적 문헌고찰 한 편은 논문 수십~수백 편을 정리한 것이라, 개별 실험보다 분야 전체가 어디로 가는지 잘 보인다. 최대 3편. <b>고를 때</b>: 목록에 약탈적/저품질 학술지가 섞여 있다. 저널 평판과 초록의 구체성(몇 편을 어떤 DB에서 어떤 기준으로 골랐는지 밝히는가)을 보고 골라라. 초등·K-12와 무관한 것은 버려라. 쓸 만한 게 1편뿐이면 1편만 써라 — 숫자를 채우지 마라. 편당 <b>제목</b>(링크) — 저널, 연도, 인용수. 그리고 <b>무엇을 정리했나</b> 2문장: 몇 편을 어떤 기준으로 훑었고, 그래서 이 분야에 대해 무슨 결론을 내렸는지. 개별 실험 결과가 아니라 <i>종합된 판단</i>을 전해라. 비었으면 "최근 30일 신규 리뷰 없음"만 써라.
3. <h2>읽을 만한 논문 5편</h2> — 이 목록은 최신순이 아니라 <b>정확도순</b>(최근 1년)이다. 새로 나왔다는 이유로 고르지 마라.
   <b>고르는 기준 — 아래를 모두 만족하는 것만</b>:
   (가) <b>초등학교 교사</b>가 읽을 때 자기 교실과 연결점이 있는가. 대학생·성인 대상 연구는 버려라.
   (나) 주제가 AI/디지털 활용 수업, AI 윤리, 디지털 과몰입 중 하나에 실제로 닿아 있는가.
   (다) <b>시사점이 있는가</b> — 수업 설계·생활지도·학교 규칙 중 무엇이든 "그래서 나는 무엇을 다르게 할 수 있나"에 답이 되는가.
        현상만 기술하고 끝나는 연구, 시사점이 "더 많은 연구가 필요하다"뿐인 연구는 버려라.
   다섯 편을 억지로 채우지 마라. 기준을 통과하는 게 3편뿐이면 3편만 써라.
   편당 아래 3줄 구조를 지켜라:
   - <b>제목</b>(링크) — 저널, 연도. 열람 링크를 PDF/본문/DOI 순으로 붙여라.
   - <b>쉽게 말하면</b>: 전문용어 없이 2문장. "~를 알아보려고 ~명에게 ~를 시켜봤더니 ~였다" 형태. 통계 용어는 "차이가 꽤 컸다" 식으로 풀어라. 이건 정독용이 아니라 <i>어느 걸 읽을지 고르기 위한</i> 요약이다.
   - <b>교실에 주는 시사점</b>: 이 논문을 읽고 초등 교사가 무엇을 다르게 할 수 있는지 1~2문장. 구체적으로. 표본·설계의 한계가 그 시사점을 제한한다면 그것도 한 줄.
4. <h2>이론적 배경 후보</h2> — 공통인용 문헌 표(문헌[doi로 링크] / 연도 / 이번 주 공동인용 수 / 어떤 이론적 역할). 여러 신규 논문이 동시에 인용했다는 건 그게 이 분야의 공통 전제라는 뜻임을 짚어줘라.
5. <h2>국내 동향</h2> — 목록에 제목·학회·DOI만 있고 초록이 없다. 제목마다 url 필드로 링크를 걸어라. 내용을 지어내지 말고 제목과 학회명에서 읽히는 것만(어떤 주제가 몰려 있는지, 해외와 관심사가 겹치는지/다른지) 짚어라. 비었으면 "최근 30일 신규 없음"만 써라.
6. <h2>KERIS 디지털교육 동향</h2> — 월간 리포트라 대부분의 주는 지난주와 같은 호다. is_new가 true면 "새 호가 나왔습니다"로 시작하고, false면 "최신호는 여전히 N호입니다"로 한 줄만 쓴다. 제목을 url로 링크하고 파일 크기(mb)를 괄호로 덧붙여라. 내용은 받아보지 않았으니 <b>무슨 내용인지 추측하지 마라</b> — 제목에 있는 것만 쓴다. 마지막에 "정독하려면 내려받아 eli5.py에 넣으세요" 한 줄. 데이터가 null이면 "이번 주 확인 실패"만 써라.

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


PAGE_CSS = """
  /* Gmail은 CSS 변수(var())를 제거한다. 색은 전부 literal로 쓴다. */
  body{font:16px/1.75 -apple-system,BlinkMacSystemFont,'Segoe UI','Malgun Gothic',sans-serif;
       max-width:720px;margin:0 auto;padding:32px 20px;color:#1f2328;background:#fff;
       word-break:keep-all}   /* 한글이 단어 중간에서 끊기지 않게 */
  h1{font-size:1.7rem;letter-spacing:-.02em;margin:0 0 .2em}
  h2{font-size:1.2rem;margin:2.4em 0 .8em;padding-bottom:.35em;border-bottom:2px solid #d8dee4}
  li{margin:.45em 0}
  strong{font-weight:650;color:#0b1117}
  a{color:#0969da}
  table{border-collapse:collapse;width:100%;font-size:.94em}
  td,th{border:1px solid #d8dee4;padding:7px 11px;text-align:left}
  th{background:#f6f8fa}

  /* 본문에서 쓰는 강조 */
  .key{background:#fff3c4;padding:0 .18em;border-radius:2px}          /* 형광펜 */
  .num{font-family:ui-monospace,Consolas,monospace;font-size:.92em;color:#57606a}
  .callout{border-left:4px solid #0969da;background:#f2f7fd;padding:.9em 1.1em;
           margin:1.5em 0;border-radius:0 6px 6px 0}
  .warn{border-left:4px solid #bf8700;background:#fff8e6;padding:.9em 1.1em;
        margin:1.5em 0;border-radius:0 6px 6px 0}

  figure{margin:1.9em 0;text-align:center}
  figure svg{max-width:100%;height:auto}
  figcaption{font-size:.88em;color:#57606a;margin-top:.7em;text-align:center}

  @media (prefers-color-scheme:dark){
    body{background:#0d1117;color:#e6edf3}
    h2{border-color:#30363d} strong{color:#fff} a{color:#58a6ff}
    td,th{border-color:#30363d} th{background:#161b22}
    .key{background:#4a3a00;color:#ffe9a8}
    .callout{background:#0d1d2e;border-color:#388bfd}
    .warn{background:#2b2100;border-color:#d29922}
    .num,figcaption{color:#9198a1}
  }

  /* 브라우저 Ctrl+P -> PDF 저장용 */
  @page{margin:2cm}
  @media print{
    body{background:#fff;color:#000;max-width:none;padding:0}
    a{color:#000;text-decoration:underline}
    figure,li,tr{break-inside:avoid} h2{break-after:avoid}
  }
"""


def render(fragment, archive_url=None, title="컴퓨터교육·AI교육 주간 브리핑"):
    """조각 -> 독립 HTML 문서. 메일 본문, 아카이브, eli5 페이지가 같은 걸 쓴다."""
    back = f'<p style="font-size:.9em"><a href="{archive_url}">웹에서 보기 / PDF로 저장</a></p>' if archive_url else ""
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{title}</title><style>{PAGE_CSS}</style></head>'
            f'<body><h1>{title}</h1>'
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
                f'<title>논문 브리핑 아카이브</title><style>{PAGE_CSS}</style></head>'
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
    picks = papers()
    revs, keris = reviews(), keris_report()
    print(f"토픽 {len(trends)} / 논문 {len(picks)} / 리뷰 {len(revs)} / "
          f"KERIS {'통권 ' + str(keris.get('issue')) if keris else '실패'}", file=sys.stderr)
    doc = render(summarize(trends, picks, foundations(picks), domestic(), revs, keris),
                 pages_url())
    archive(doc)
    print(f"docs/{date.today()}.html 저장", file=sys.stderr)
    if "--dry-run" not in sys.argv:
        send(doc)


if __name__ == "__main__":
    main()
