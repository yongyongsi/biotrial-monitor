from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import scheduler as sched
from app.api.demo import router as demo_router
from app.api.routes import data_router, router as api_router
from app.config import settings
from app.db import Base, engine
from app.schema_sync import sync as sync_schema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
log = logging.getLogger("biotrial")

# httpx 는 요청 URL 을 INFO 로 남기는데, 거기에 DART 인증키가 그대로 들어간다.
# 로그 파일에 키가 남지 않도록 경고 이상만 남긴다.
for _noisy in ("httpx", "httpcore", "apscheduler.executors.default"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    sync_schema(engine)
    log.info("데이터베이스 준비 완료")
    sched.start()
    yield
    sched.shutdown()


app = FastAPI(
    title="바이오 임상시험 모니터",
    description="관심 신약의 임상시험 상태 변화를 가장 빠르게 감지한다.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(data_router)
app.include_router(demo_router)


# 화면을 직접 서빙한다.
#   휴대폰(Termux) 에는 Node.js 를 깔 수 없으므로,
#   PC 에서 미리 만들어 둔 정적 파일을 FastAPI 가 그대로 내보낸다.
#   (Docker 구성에서는 이 폴더가 없고 Next.js 서버가 따로 뜬다)
STATIC_DIR = Path(os.getenv("STATIC_DIR", str(Path(__file__).resolve().parent.parent / "static")))

if STATIC_DIR.is_dir() and (STATIC_DIR / "index.html").exists():
    # API 라우터를 먼저 등록한 뒤에 마운트해야 /api/* 가 가려지지 않는다.
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")
    log.info("화면을 직접 서빙합니다: %s", STATIC_DIR)
else:
    @app.get("/")
    def root():
        return {"service": "bio-trial-monitor", "docs": "/docs", "api": "/api/dashboard"}
