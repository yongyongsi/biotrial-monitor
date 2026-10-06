"""
초기 데이터 투입.

여기 들어가는 값은 전부 2026-09-27 에 공식 출처에서 실제로 확인한 것이다
(docs/00_RESEARCH.md). 추측으로 만든 임상시험은 하나도 없다.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine, session_scope
from app.schema_sync import sync as sync_schema
from app.models import (
    ClinicalTrial, Company, Disease, Drug, Source, Watchlist,
)

log = logging.getLogger(__name__)

SOURCES = [
    # code, 이름, 종류, 지역, 공식여부, 수집레벨, base_url, 주기(초), robots허용
    ("ctgov", "미국 임상시험 등록소 (ClinicalTrials.gov)", "REGISTRY", "GLOBAL", True, 1,
     "https://clinicaltrials.gov/api/v2", 3600, True),
    ("openfda", "미국 식품의약국 공개데이터 (openFDA)", "REGULATOR", "GLOBAL", True, 1,
     "https://api.fda.gov", 10800, True),
    ("europepmc", "유럽 학술문헌 데이터베이스 (Europe PMC)", "JOURNAL", "GLOBAL", True, 1,
     "https://www.ebi.ac.uk/europepmc/webservices/rest", 43200, True),
    ("opendart", "금융감독원 전자공시 (DART)", "COMPANY", "KR", True, 1,
     "https://opendart.fss.or.kr/api", 3600, True),
    ("hyundaibio", "현대바이오사이언스 공식 공지", "COMPANY", "KR", True, 3,
     "https://hyundaibioscience.com/notice", 3600, True),
    ("who_news", "세계보건기구 뉴스 (WHO)", "REGULATOR", "GLOBAL", True, 2,
     "https://www.who.int/rss-feeds/news-english.xml", 10800, True),
    ("statnews", "STAT News", "NEWS", "GLOBAL", False, 2,
     "https://www.statnews.com/feed/", 10800, True),
    ("medipana", "메디파나뉴스", "NEWS", "KR", False, 2,
     "https://www.medipana.com/rss/allArticle.xml", 21600, True),
    ("dailypharm", "데일리팜", "NEWS", "KR", False, 2,
     "https://www.dailypharm.com/rss/rss.php", 21600, True),
    ("hitnews", "히트뉴스", "NEWS", "KR", False, 2,
     "https://www.hitnews.co.kr/rss/allArticle.xml", 21600, True),
    # robots.txt 가 Disallow:/ 이므로 크롤링하지 않는다. 공식 API/벌크 경로만 사용.
    ("cris", "국내 임상연구정보서비스 (CRIS)", "REGISTRY", "KR", True, 1,
     "https://cris.nih.go.kr", 21600, False),
    ("who_ictrp", "WHO 국제 임상시험 등록 플랫폼 (ICTRP)", "REGISTRY", "GLOBAL", True, 1,
     "https://trialsearch.who.int", 86400, False),
]


def seed(db: Session) -> None:
    # ---- 소스
    for (code, name, stype, region, official, level, url, interval, robots) in SOURCES:
        if db.scalars(select(Source).where(Source.code == code)).first():
            continue
        db.add(Source(code=code, name_ko=name, source_type=stype, region=region,
                      is_official=official, collection_level=level, base_url=url,
                      poll_interval_sec=interval, robots_allowed=robots))
    db.flush()

    # ---- 기업
    # DART 고유번호(corp_code)는 2026-09-27 corpCode.xml 에서 실제 확인한 값이다.
    # 페니트리움바이오는 현대바이오와 별개로 상장된 회사이므로 따로 관리한다.
    companies = {}
    for name_ko, name_en, corp_code, stock, aliases, ir in [
        ("현대바이오사이언스", "Hyundai Bioscience Co., Ltd.", "00313649", "048410",
         ["현대바이오", "현대바이오사이언스", "Hyundai Bioscience", "Hyundai Bio",
          "HyundaiBio", "048410"],
         "https://hyundaibioscience.com/notice"),
        ("페니트리움바이오", "Penetrium Bio", "01409022", "187660",
         ["페니트리움바이오", "페니트리움", "Penetrium Bio", "Penetrium", "187660",
          "현대ADM바이오"],
         None),
    ]:
        c = db.scalars(select(Company).where(Company.name_ko == name_ko)).first()
        if c is None:
            c = Company(name_ko=name_ko, name_en=name_en, dart_corp_code=corp_code,
                        aliases=aliases + [stock], ir_url=ir)
            db.add(c)
            db.flush()
        else:
            c.name_en, c.dart_corp_code = name_en, corp_code
            c.aliases = aliases + [stock]
            if ir:
                c.ir_url = ir
            db.flush()
        companies[name_ko] = c
    company = companies["현대바이오사이언스"]

    # ---- 약물 (요구사항 2-2: 명칭이 여러 가지인 문제를 aliases 로 흡수)
    drugs = {}
    for name_ko, name_en, dev_code, aliases in [
        ("제프티", "Xafty", "CP-COV03",
         ["제프티", "Xafty", "CP-COV03", "CP COV03", "CPCOV03",
          "niclosamide", "니클로사마이드"]),
        # 공시 원문 표기는 Penetrium(TM). 언론의 "Penitrium" 은 오기이므로 둘 다 넣는다.
        ("페니트리움", "Penetrium", "CP-PCA07",
         ["페니트리움", "Penetrium", "Penitrium", "CP-PCA07", "CP PCA07", "CPPCA07",
          "페니트리움바이오", "Penetrium Bio", "IND 183600"]),
    ]:
        owner = companies["페니트리움바이오"] if name_ko == "페니트리움" else company
        d = db.scalars(select(Drug).where(Drug.name_ko == name_ko)).first()
        if d is None:
            d = Drug(name_ko=name_ko, name_en=name_en, dev_code=dev_code,
                     aliases=aliases, company_id=owner.id)
            db.add(d)
        else:
            # 검색어 사전은 조사하면서 계속 늘어난다. 재실행하면 항상 최신으로 맞춘다.
            d.name_en, d.dev_code, d.aliases = name_en, dev_code, aliases
            d.company_id = owner.id
        db.flush()
        drugs[name_ko] = d

    # ---- 질환
    diseases = {}
    for name_ko, name_en, aliases in [
        ("댕기열", "Dengue", ["댕기열", "뎅기열", "Dengue", "dengue fever", "DENV"]),
        ("거세저항성 전립선암", "Castration-Resistant Prostate Cancer",
         ["전립선암", "CRPC", "prostate cancer", "거세저항성"]),
        ("에볼라", "Ebola", ["에볼라", "Ebola", "EVD"]),
        ("코로나19", "COVID-19", ["코로나", "COVID-19", "COVID", "SARS-CoV-2"]),
        ("인플루엔자", "Influenza", ["독감", "인플루엔자", "Influenza", "flu"]),
        ("재발성·불응성 진행성 고형암", "Relapsed/Refractory Advanced Solid Tumor",
         ["고형암", "solid tumor", "불응성", "재발성", "펨브롤리주맙", "pembrolizumab",
          "키트루다", "Keytruda"]),
    ]:
        d = db.scalars(select(Disease).where(Disease.name_ko == name_ko)).first()
        if d is None:
            d = Disease(name_ko=name_ko, name_en=name_en, aliases=aliases)
            db.add(d)
        else:
            d.name_en, d.aliases = name_en, aliases
        db.flush()
        diseases[name_ko] = d

    # ---- 임상시험 (2026-09-27 ClinicalTrials.gov 에서 실제 확인한 2건)
    trials = [
        dict(registry="CTGOV", registry_id="NCT07576868", org_study_id="DEN-201",
             url="https://clinicaltrials.gov/study/NCT07576868",
             title_ko="제프티 댕기열 치료 임상시험 (베트남)",
             drug="제프티", disease="댕기열", country="Vietnam", region="GLOBAL",
             watch=True),
        dict(registry="CTGOV", registry_id="NCT07683013", org_study_id="ADM-PC-001",
             url="https://clinicaltrials.gov/study/NCT07683013",
             title_ko="페니트리움 거세저항성 전립선암 임상 1상 (서울대병원)",
             drug="페니트리움", disease="거세저항성 전립선암",
             country="South Korea", region="KR", watch=True),
    ]
    for t in trials:
        row = db.scalars(
            select(ClinicalTrial).where(ClinicalTrial.registry_id == t["registry_id"])
        ).first()
        if row is None:
            row = ClinicalTrial(
                registry=t["registry"], registry_id=t["registry_id"],
                org_study_id=t["org_study_id"], url=t["url"], title_ko=t["title_ko"],
                drug_id=drugs[t["drug"]].id, disease_id=diseases[t["disease"]].id,
                company_id=company.id, country=t["country"], region=t["region"],
                is_watchlisted=t["watch"],
            )
            db.add(row)
            db.flush()

    # ---- 관심 목록 (요구사항 17)
    wl = [("DRUG", drugs["제프티"].id, "제프티 (Xafty)", 0),
          ("DRUG", drugs["페니트리움"].id, "페니트리움 (Penetrium)", 1),
          ("DISEASE", diseases["댕기열"].id, "댕기열", 2),
          ("COMPANY", company.id, "현대바이오사이언스 (048410)", 3),
          ("COMPANY", companies["페니트리움바이오"].id, "페니트리움바이오 (187660)", 4)]
    for kind, ref_id, label, order in wl:
        exists = db.scalars(
            select(Watchlist).where(Watchlist.kind == kind, Watchlist.ref_id == ref_id)
        ).first()
        if exists is None:
            db.add(Watchlist(kind=kind, ref_id=ref_id, label_ko=label, sort_order=order))
        else:
            exists.label_ko, exists.sort_order = label, order
    db.flush()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    sync_schema(engine)
    with session_scope() as db:
        seed(db)
    log.info("초기 데이터 투입 완료")
    log.info("  소스 %d개 / 임상시험 2건 (NCT07576868, NCT07683013)", len(SOURCES))


if __name__ == "__main__":
    main()
