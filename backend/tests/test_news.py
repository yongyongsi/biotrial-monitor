"""
뉴스 걸러내기 검증.

구글뉴스 검색은 본문·연관도까지 보기 때문에 제목과 무관한 글이 섞여 온다.
아래 제목들은 2026-10-06 실제 검색 결과에서 그대로 가져온 것이다.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.collectors import news
from app.core import severity as sev

KEYWORDS = ["현대바이오", "현대바이오사이언스", "페니트리움", "제프티",
            "Xafty", "CP-COV03", "Penetrium"]


# --- 진짜 가져와야 할 것 (실제 검색 결과) --------------------------------
@pytest.mark.parametrize("title", [
    '페니트리움 "항암제 \'가짜 내성\' 확인…병용 효과"',
    "폐암 세계 석학 “페니트리움, ‘애드온’ 항암치료제로서 잠재력 충분”",
    "현대바이오, ‘페니트리움’ 전립선암 임상 1상 첫 환자 투약",
    "페니트리움바이오, 미국 FDA에 항암신약 임상 2a상 신청",
    "현대바이오 제프티, 인체 폐 조직 모델서 항바이러스 효능 재확인",
    "씨앤팜, 현대바이오 주식담보 계약변경·주요계약 지분 7.76%로 축소",
])
def test_관심_뉴스는_통과한다(title):
    assert news.is_relevant(title, KEYWORDS) is True


# --- 걸러내야 할 것 (실제로 섞여 온 노이즈) ------------------------------
@pytest.mark.parametrize("title", [
    "오토만 제국의 반지 기본 배경과 특수 화면 비교",       # 완전 무관
    "대한민국 대표 가치투자포털 - 아이투자",                # 제목에 대상 없음
    "현대바이오랜드 주가, 상한가... 무슨 회사길래?",         # 이름만 비슷한 다른 회사
    "현대바이오랜드, 3분기 실적 발표",
    "",
])
def test_무관한_뉴스는_걸러낸다(title):
    assert news.is_relevant(title, KEYWORDS) is False


def test_다른회사라도_진짜_대상이_함께_있으면_남긴다():
    """'현대바이오랜드' 가 들어 있어도 페니트리움 얘기면 버리면 안 된다."""
    title = "현대바이오랜드와 현대바이오, 페니트리움 임상 협력 발표"
    assert news.is_relevant(title, KEYWORDS) is True


# --- 중요도 ---------------------------------------------------------------
def test_임상_관련은_참고등급이다():
    """뉴스는 공식 확인이 아니므로 CRITICAL 로 올리지 않는다 (요구사항 13, 15)."""
    assert news.classify("페니트리움바이오, 미국 FDA에 임상 2a상 신청") == sev.MEDIUM
    assert news.classify("현대바이오, 전립선암 임상 1상 첫 투약") == sev.MEDIUM


def test_단순_주가기사는_일반등급이다():
    assert news.classify("현대바이오 주가 소폭 상승 마감") == sev.LOW


def test_뉴스는_절대_CRITICAL이_되지_않는다():
    """보도만으로는 사실 확정이 아니다. 공식 출처에서 확인돼야 한다."""
    for t in ["현대바이오 FDA 승인 임박", "페니트리움 임상 중단설", "제프티 품목허가 완료"]:
        assert news.classify(t) != sev.CRITICAL


# --- RSS 파싱 -------------------------------------------------------------
SAMPLE = """<rss><channel>
<item>
  <title>페니트리움 "항암제 '가짜 내성' 확인…병용 효과" - 연합뉴스</title>
  <link>https://news.google.com/rss/articles/ABC123</link>
  <pubDate>Sun, 14 Sep 2026 01:23:45 GMT</pubDate>
  <source url="https://www.yna.co.kr">연합뉴스</source>
</item>
<item>
  <title>Hyundai Bioscience gets FDA nod - Korea Herald</title>
  <link>https://news.google.com/rss/articles/DEF456</link>
  <pubDate>Mon, 15 Sep 2026 02:00:00 GMT</pubDate>
  <source url="https://koreaherald.com">Korea Herald</source>
</item>
</channel></rss>"""


def test_RSS를_읽어낸다():
    items = news.parse_rss(SAMPLE)
    assert len(items) == 2
    first = items[0]
    assert first["source"] == "연합뉴스"
    # 제목 뒤에 붙은 언론사 이름은 떼어낸다
    assert first["title"].endswith('병용 효과"')
    assert " - 연합뉴스" not in first["title"]
    assert first["published_at"].year == 2026
    assert first["published_at"].month == 9


def test_국내_해외를_구분한다():
    items = news.parse_rss(SAMPLE)
    assert news.is_domestic(items[0]["source"], items[0]["title"]) is True
    assert news.is_domestic(items[1]["source"], items[1]["title"]) is False


@pytest.mark.parametrize("outlet,title", [
    ("v.daum.net", "페니트리움 미국 2a상 합류"),       # 도메인으로 오는 국내 매체
    ("news.mt.co.kr", "현대바이오 임상 소식"),
    ("", "현대바이오, 전립선암 임상 1상 투약"),          # 매체 미상이어도 한글이면 국내
    ("연합뉴스", "Penetrium update"),
])
def test_도메인으로_와도_국내로_본다(outlet, title):
    assert news.is_domestic(outlet, title) is True


def test_해외_매체는_해외로_둔다():
    assert news.is_domestic("Reuters", "Hyundai Bioscience gets FDA nod") is False
    assert news.is_domestic("fiercebiotech.com", "Penetrium Phase 2a cleared") is False


def test_같은_기사는_같은_지문을_갖는다():
    when = datetime(2026, 9, 14, tzinfo=timezone.utc)
    a = news.fingerprint("페니트리움, 항암제 가짜 내성 확인", when)
    b = news.fingerprint("페니트리움 항암제 가짜내성 확인!", when)
    assert a == b          # 기호·띄어쓰기 차이는 무시한다


def test_다른_날_기사는_다른_지문이다():
    t = "페니트리움 임상 1상 투약"
    a = news.fingerprint(t, datetime(2026, 9, 14, tzinfo=timezone.utc))
    b = news.fingerprint(t, datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert a != b


# ---------------------------------------------------------------------------
# 해외 보도 (영문)
#
# 한국어만 검색하면 통째로 놓치는 것이 있다. 아래는 2026-10-07 실제 검색 결과.
# 특히 에볼라 소식은 국내 뉴스에 거의 없고 영문으로만 나왔다.
# ---------------------------------------------------------------------------
# 실제 시스템은 약물 별칭까지 검색어로 쓴다 (제프티 = 니클로사마이드 기반)
EN_KEYWORDS = KEYWORDS + ["Hyundai Bioscience", "Penetrium Bioscience", "XAFTY",
                          "niclosamide"]


@pytest.mark.parametrize("title", [
    "Hyundai Bioscience Discloses XAFTY®'s IC50 Data for Ebola",
    "Hyundai Bioscience Confirms Entry into U.S. FDA Phase 2 Trials",
    "Hyundai Bioscience joins dengue fever clinical trial in Vietnam",
    "Penetrium Bioscience to unveil global Phase 2 trial strategy",
    "Penetrium Bioscience Unveils Breakthrough Mechanism Solving 13-year puzzle",
])
def test_영문_관심_뉴스도_통과한다(title):
    assert news.is_relevant(title, EN_KEYWORDS) is True


@pytest.mark.parametrize("title", [
    "Hyundai Motor unveils new electric SUV lineup",      # 자동차 회사
    "Samsung Biologics signs contract with Pfizer",       # 다른 회사
    "Pfizer reports strong Q3 oncology results",
])
def test_무관한_영문_뉴스는_걸러낸다(title):
    assert news.is_relevant(title, EN_KEYWORDS) is False


def test_기반물질_이름만_있어도_가져온다():
    """제프티는 니클로사마이드 기반이고 에볼라는 관심 질환 2순위다.
    회사 이름이 없어도 놓치면 안 된다."""
    assert news.is_relevant("Niclosamide Shows Antiviral Activity Against Ebola",
                            EN_KEYWORDS) is True


def test_영문_제목도_임상_관련이면_등급이_올라간다():
    assert news.classify("Hyundai Bioscience Confirms Entry into U.S. FDA Phase 2 Trials") == sev.MEDIUM
    assert news.classify("Penetrium Bioscience to unveil global Phase 2 trial strategy") == sev.MEDIUM
    assert news.classify("Enterprise value to EBIT forward of Penetrium Bioscience") == sev.LOW


def test_영문_제목은_해외로_분류된다():
    assert news.is_domestic("Korea Biomedical Review",
                            "Hyundai Bioscience Discloses XAFTY IC50 Data") is False
    assert news.is_domestic(None,
                            "Penetrium Bioscience to unveil global Phase 2") is False


def test_검색_지역에_따라_주소가_달라진다():
    ko = news.RSS_URL.format(q="test", **news.LOCALES["ko"])
    en = news.RSS_URL.format(q="test", **news.LOCALES["en"])
    assert "hl=ko" in ko and "gl=KR" in ko
    assert "hl=en-US" in en and "gl=US" in en
    assert ko != en


# ---------------------------------------------------------------------------
# 베트남 현지 보도
#
# 댕기열 임상(NCT07576868)이 베트남 2개 기관에서 진행 중이라
# 현지 보도가 국내보다 빠를 수 있다. 아래는 2026-10-08 실제 검색 결과.
# ---------------------------------------------------------------------------
VI_KEYWORDS = EN_KEYWORDS + ["Hyundai Bioscience"]


def test_베트남어_제목도_가져온다():
    title = ("Khởi động thử nghiệm lâm sàng thuốc kháng virus điều trị sốt xuất huyết "
             "của Hyundai Bioscience")
    assert news.is_relevant(title, VI_KEYWORDS) is True


def test_베트남_매체는_해외로_분류된다():
    assert news.is_domestic("vnexpress.net", "Thử nghiệm lâm sàng") is False
    assert news.is_domestic("Báo Tuổi Trẻ", "Hyundai Bioscience thử nghiệm") is False


@pytest.mark.parametrize("outlet,title,expected", [
    (None, "현대바이오 임상 소식", "ko"),
    ("vnexpress.net", "Thử nghiệm lâm sàng thuốc", "vi"),
    (None, "Việt Nam thử nghiệm lâm sàng thuốc điều trị sốt xuất huyết", "vi"),
    ("Reuters", "Hyundai Bioscience gets FDA nod", "en"),
])
def test_제목_언어를_알아본다(outlet, title, expected):
    assert news.language_of(outlet, title) == expected


def test_베트남어_임상_단어도_등급을_올린다():
    assert news.classify(
        "Khởi động thử nghiệm lâm sàng thuốc kháng virus điều trị sốt xuất huyết"
    ) == sev.MEDIUM


def test_세_지역_주소가_모두_다르다():
    urls = {loc: news.RSS_URL.format(q="x", **cfg) for loc, cfg in news.LOCALES.items()}
    assert len(set(urls.values())) == 3
    assert "gl=VN" in urls["vi"] and "hl=vi" in urls["vi"]
