"""
화면이 읽을 데이터를 파일로 뽑아낸다.

GitHub Pages 에는 서버가 없다. 그래서 FastAPI 가 만들던 응답을
그대로 JSON 파일로 저장해 두고, 화면이 그 파일을 읽게 한다.

    /api/dashboard?days=0        ->  data/dashboard-0.json
    /api/trials/NCT07576868      ->  data/trials/NCT07576868.json

API 와 같은 함수를 쓰므로 화면에 보이는 내용이 서버 방식과 완전히 같다.
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.api.routes import dashboard, list_disclosures, trial_detail
from app.db import engine, session_scope
from app.models import ClinicalTrial
from app.schema_sync import sync as sync_schema

log = logging.getLogger("export")

# 화면의 기간 선택 버튼과 같은 값 (0 = 오늘)
PERIODS = (0, 3, 7, 30)


def write(path: Path, payload) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def export(out_dir: Path, site_src: Path | None = None) -> dict:
    sync_schema(engine)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 화면 파일(HTML/CSS/JS)을 함께 복사
    if site_src and site_src.is_dir():
        for item in site_src.iterdir():
            dest = out_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

    data_dir = out_dir / "data"
    total = 0
    counts = {"dashboard": 0, "trials": 0}

    with session_scope() as db:
        for days in PERIODS:
            total += write(data_dir / f"dashboard-{days}.json", dashboard(days=days, db=db))
            counts["dashboard"] += 1

        for trial in db.scalars(select(ClinicalTrial)).all():
            total += write(data_dir / "trials" / f"{trial.registry_id}.json",
                           trial_detail(trial.registry_id, db=db))
            counts["trials"] += 1

        total += write(data_dir / "disclosures.json",
                       list_disclosures(days=365, limit=200, db=db))

    total += write(data_dir / "meta.json", {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "periods": list(PERIODS),
    })

    counts["bytes"] = total
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="화면용 데이터 파일을 만든다")
    parser.add_argument("--out", default="site", help="내보낼 폴더")
    parser.add_argument("--site", default=None,
                        help="복사해 넣을 화면 파일 폴더 (frontend/out)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    result = export(Path(args.out), Path(args.site) if args.site else None)
    log.info("내보내기 완료: 대시보드 %d개 / 임상시험 %d개 / %.1fKB",
             result["dashboard"], result["trials"], result["bytes"] / 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
