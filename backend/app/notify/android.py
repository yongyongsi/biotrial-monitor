"""
갤럭시(안드로이드) 자체 알림.

Termux:API 가 설치돼 있으면 `termux-notification` 으로 폰 알림창에 직접 띄운다.
텔레그램 같은 외부 서비스가 필요 없고, 인터넷이 끊겨도 동작한다.
"""
from __future__ import annotations

import logging
import re
import shlex
import shutil
import subprocess
from typing import Optional

log = logging.getLogger(__name__)

_BIN = "termux-notification"

# 중요도 -> 안드로이드 알림 우선순위
_PRIORITY = {"CRITICAL": "max", "HIGH": "high", "MEDIUM": "default", "LOW": "low"}
_ICON = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "⚪"}

# termux-notification 의 --action 값은 Termux 가 **셸 명령으로 실행**한다.
# URL 은 우리가 조립하지만 그 안의 등록번호/접수번호는 외부 API 에서 온 값이다.
# 그 값에 세미콜론 같은 문자가 섞여 들어오면 임의 명령이 실행될 수 있으므로,
# 알림에 넣기 전에 주소 형태를 엄격히 검사한다.
_SAFE_URL = re.compile(
    r"^https://(?:[a-z0-9-]+\.)*(?:clinicaltrials\.gov|dart\.fss\.or\.kr|fda\.gov)"
    r"(?:/[A-Za-z0-9._~\-/]*)?(?:\?[A-Za-z0-9._~\-=&]*)?$"
)
_LOCAL_URL = "http://localhost:8000"


def safe_url(url: Optional[str]) -> Optional[str]:
    """알림 버튼에 넣어도 되는 주소인지 확인한다. 아니면 None."""
    if not url:
        return None
    url = url.strip()
    if url == _LOCAL_URL:
        return url
    if len(url) > 300 or not _SAFE_URL.match(url):
        log.warning("알림에 넣기에 안전하지 않은 주소라 버튼을 뺍니다: %.80s", url)
        return None
    return url


def available() -> bool:
    """Termux:API 가 설치돼 있는가."""
    return shutil.which(_BIN) is not None


def notify(title: str, body: str, severity: str = "HIGH",
           url: Optional[str] = None, group: str = "biotrial",
           notif_id: Optional[str] = None) -> bool:
    """폰 알림창에 띄운다.

    priority 가 high/max 여야 화면 위에 잠깐 떠오르는 '배너'로 나온다.
    default 이하면 알림창에 조용히 쌓이기만 한다.
    """
    if not available():
        return False

    priority = _PRIORITY.get(severity, "default")
    cmd = [
        _BIN,
        "--title", title[:80],            # 배너는 짧아야 한 줄에 다 보인다
        "--content", body[:400],
        "--priority", priority,
        "--group", group,
        # 건마다 다른 id 를 줘야 알림이 덮어쓰이지 않고 쌓인다
        "--id", notif_id or f"{group}-{abs(hash(title + body)) % 1000000}",
    ]

    # 중요한 건은 소리와 진동으로 확실히 알린다 (요구사항 20)
    if severity in ("CRITICAL", "HIGH"):
        cmd += ["--sound"]
    if severity == "CRITICAL":
        cmd += ["--vibrate", "500,200,500,200,500"]

    checked = safe_url(url)
    if checked:
        # 셸에 넘어가므로 따옴표로 감싼다 (주소 검사와 이중으로 막는다)
        quoted = shlex.quote(checked)
        cmd += [
            "--action", f"termux-open-url {quoted}",      # 알림을 누르면 원문
            "--button1", "원문 보기",
            "--button1-action", f"termux-open-url {quoted}",
            "--button2", "앱 열기",
            "--button2-action", f"termux-open-url {shlex.quote(_LOCAL_URL)}",
        ]
    try:
        subprocess.run(cmd, check=True, timeout=20,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except Exception as exc:                      # noqa: BLE001
        log.warning("안드로이드 알림 실패: %s", exc)
        return False


def summary(count: int, top_headline: str, severity: str = "HIGH") -> bool:
    """여러 건이 한꺼번에 들어왔을 때의 묶음 알림."""
    return notify(
        f"{_ICON.get(severity, '🔔')} 새 소식 {count}건",
        top_headline,
        severity,
        url=_LOCAL_URL,
        notif_id="biotrial-summary",
    )
