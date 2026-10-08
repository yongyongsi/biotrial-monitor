"""
뉴스 수집 (Tier 3).

공식 데이터(ClinicalTrials.gov·DART)만 보면 조용한 달에도 뉴스에는 소식이 있다.
실제로 2026-09 한 달간 공식 데이터는 임상 관련 0건이었지만
학회 발표·지분 변동 뉴스가 여러 건 있었다.

구글뉴스가 **공식 RSS** 를 제공하므로 크롤링이 아니라 정식 경로로 가져온다.
    https://news.google.com/rss/search?q=검색어&hl=ko&gl=KR&ceid=KR:ko

다만 검색 결과에는 노이즈가 섞인다. 실제로 걸러야 했던 것들:
    "오토만 제국의 반지 기본 배경과..."   -> 검색어와 무관한 글
    "현대바이오랜드 주가 상한가..."        -> 이름만 비슷한 다른 회사

그래서 **제목에 관심 대상이 실제로 들어 있는지** 다시 확인하고,
혼동되는 이름은 명시적으로 제외한다.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from app.config import settings
from app.core import severity as sev

log = logging.getLogger(__name__)

SOURCE_CODE = "google_news"
RSS_URL = ("https://news.google.com/rss/search"
           "?q={q}&hl={hl}&gl={gl}&ceid={gl}:{lang}")

# 검색 지역. 한국어 검색만 하면 해외 보도를 통째로 놓친다.
# 실제로 에볼라 관련 소식은 국내 뉴스에 거의 없고 영문으로만 나왔다.
LOCALES = {
    "ko": {"hl": "ko", "gl": "KR", "lang": "ko"},
    "en": {"hl": "en-US", "gl": "US", "lang": "en"},
    # 댕기열 임상이 베트남에서 돌고 있다. 현지 보도가 가장 빠를 수 있다.
    "vi": {"hl": "vi", "gl": "VN", "lang": "vi"},
}

# 이름이 비슷하지만 전혀 다른 회사·주제. 제목에 이것만 있으면 버린다.
EXCLUDE = (
    "현대바이오랜드",      # 화장품 원료 회사 (052260). 우리 관심사와 무관
    "현대바이오사이언스랜드",
)

# 임상·규제와 직접 관련된 말. 들어 있으면 중요도를 올린다.
CLINICAL_WORDS = (
    # 베트남어 — 현지 보도용
    "lâm sàng", "thử nghiệm", "phê duyệt", "điều trị", "bệnh nhân",
    "kháng virus", "sốt xuất huyết", "giai đoạn", "thuốc",
    # 한국어
    "임상", "FDA", "식약처", "승인", "허가", "IND", "투약", "환자", "학회",
    "논문", "결과", "효능", "안전성", "전임상", "병용", "적응증", "품목허가",
    # 영어 — 해외 보도용
    "trial", "phase", "approval", "approved", "clinical", "dosing", "patients",
    "efficacy", "safety", "preclinical", "combination", "antiviral", "oncology",
)
# 투자 관점에서 의미 있는 말
MATERIAL_WORDS = ("계약", "기술이전", "수출", "공급", "지분", "유상증자", "전환사채",
                  "license", "partnership", "agreement", "funding", "stake")


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=25.0, follow_redirects=True,
        headers={"User-Agent": settings.user_agent,
                 "Accept": "application/rss+xml,application/xml,text/xml"},
    )


def fetch(query: str, locale: str = "ko") -> List[Dict[str, Any]]:
    """검색어 하나에 대한 뉴스 목록. locale 은 'ko' 또는 'en'."""
    loc = LOCALES.get(locale, LOCALES["ko"])
    try:
        with _client() as c:
            r = c.get(RSS_URL.format(q=quote(query), **loc))
            r.raise_for_status()
            body = r.text
    except Exception as exc:                       # noqa: BLE001
        log.warning("뉴스 조회 실패 (%s): %s", query, exc)
        return []
    return parse_rss(body)


_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
_FIELD = {
    "title": re.compile(r"<title>(.*?)</title>", re.S),
    "link": re.compile(r"<link>(.*?)</link>", re.S),
    "pub": re.compile(r"<pubDate>(.*?)</pubDate>", re.S),
    "source": re.compile(r"<source[^>]*>(.*?)</source>", re.S),
}


def _clean(text: str) -> str:
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def parse_rss(body: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in _ITEM.findall(body):
        item: Dict[str, Any] = {}
        for key, pat in _FIELD.items():
            m = pat.search(raw)
            item[key] = _clean(m.group(1)) if m else None
        if not item.get("title") or not item.get("link"):
            continue
        item["published_at"] = _parse_date(item.pop("pub", None))
        # 구글뉴스 제목은 "제목 - 언론사" 형태다. 언론사를 떼어낸다.
        title, outlet = item["title"], item.get("source")
        if outlet and title.endswith(f" - {outlet}"):
            item["title"] = title[: -(len(outlet) + 3)].strip()
        out.append(item)
    return out


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            dt = datetime.strptime(value.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# 걸러내기
# ---------------------------------------------------------------------------
def is_relevant(title: str, keywords: List[str]) -> bool:
    """제목에 관심 대상이 실제로 들어 있는가.

    구글뉴스 검색은 본문·연관도까지 보기 때문에 제목과 무관한 글이 섞여 온다.
    제목으로 한 번 더 확인하는 것이 가장 확실한 필터였다.
    """
    if not title:
        return False
    low = title.lower()

    # 이름만 비슷한 다른 회사 제외 — 단, 진짜 관심 대상도 함께 있으면 남긴다
    for bad in EXCLUDE:
        if bad in title:
            others = [k for k in keywords if k and k.lower() in low and k not in bad]
            if not others:
                return False

    return any(k and k.lower() in low for k in keywords)


def classify(title: str) -> str:
    """뉴스 중요도.

    요구사항 13 에 따라 뉴스는 기본 MEDIUM 이다.
    공식 확인이 아니라 보도이므로 CRITICAL 로 올리지 않는다
    (올리려면 공식 출처에서 확인돼야 한다).
    """
    low = title.lower()
    if any(w.lower() in low for w in CLINICAL_WORDS):
        return sev.MEDIUM
    if any(w.lower() in low for w in MATERIAL_WORDS):
        return sev.MEDIUM
    return sev.LOW


# 매체 이름이 영문 도메인으로 오는 경우가 있다 (v.daum.net, news.mt.co.kr ...)
# 베트남 매체 도메인
_VN_DOMAIN = re.compile(r"(\.vn\b|vnexpress|tuoitre|thanhnien|vietnamnet|suckhoedoisong)", re.I)

_KR_DOMAIN = re.compile(
    r"(\.kr\b|daum|naver|chosun|donga|joins|joongang|hankyung|mk\.co|yna\.|"
    r"edaily|mt\.co|sedaily|fnnews|etnews|dailypharm|medipana|hitnews|kpanews|"
    r"biospectator|pharm|newsis|nate|zum|kakao)", re.I)


def is_domestic(outlet: Optional[str], title: str) -> bool:
    """국내 매체인가 (요구사항 7: 국내/해외 분리).

    매체 이름이 한글이 아니라 도메인으로 오는 경우가 있어서
    (예: v.daum.net) 제목의 언어와 도메인을 함께 본다.
    """
    if outlet and _VN_DOMAIN.search(outlet):
        return False
    if outlet:
        if re.search(r"[가-힣]", outlet):
            return True
        if _KR_DOMAIN.search(outlet):
            return True
    # 한국 언론은 한국어로 쓴다. 제목이 한글이면 국내로 본다.
    return bool(re.search(r"[가-힣]", title or ""))


# 베트남어 특유의 성조 기호. 제목 언어를 알아보는 데 쓴다.
_VI_MARKS = re.compile(r"[ạảãáàăắằẳẵặâấầẩẫậđéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ]", re.I)


def language_of(outlet: Optional[str], title: str) -> str:
    """제목 언어. 화면에 국가 표시를 붙이는 데 쓴다."""
    if re.search(r"[가-힣]", title or ""):
        return "ko"
    if _VI_MARKS.search(title or "") or (outlet and _VN_DOMAIN.search(outlet)):
        return "vi"
    return "en"


def fingerprint(title: str, published: Optional[datetime]) -> str:
    """같은 사건을 여러 매체가 보도할 때 묶기 위한 지문 (요구사항 12, 22)."""
    key = re.sub(r"[^0-9A-Za-z가-힣]+", "", (title or "").lower())[:60]
    day = published.strftime("%Y%m%d") if published else "x"
    return f"{day}:{key}"


def recent_only(items: List[Dict[str, Any]], days: int = 60) -> List[Dict[str, Any]]:
    cut = datetime.now(timezone.utc) - timedelta(days=days)
    return [i for i in items
            if i.get("published_at") is None or i["published_at"] >= cut]
