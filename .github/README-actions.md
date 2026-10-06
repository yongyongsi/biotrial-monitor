# 자동 수집이 어떻게 도는가

```
GitHub Actions (1시간마다)
  ├─ gh-pages 가지에서 지난 데이터베이스 가져오기   ← 과거 스냅샷이 있어야 변화를 안다
  ├─ ClinicalTrials.gov / DART 수집
  ├─ 화면용 JSON 만들기 (site/ + data/ → public/)
  └─ gh-pages 가지로 밀어넣기 (항상 1개 커밋 = 용량 안 늘어남)
                  ↓
         GitHub Pages 가 그대로 웹에 제공
```

- `site/` 는 미리 빌드해 둔 화면이다. 화면을 고쳤을 때만 다시 만들어 커밋한다.
  ```bash
  cd frontend && NEXT_EXPORT=1 NEXT_PUBLIC_BASE_PATH=/저장소이름 npm run build
  cd .. && rm -rf site && cp -R frontend/out site
  ```
- 수집 주기는 `collect.yml` 의 `cron` 에서 바꾼다. GitHub 사정으로 10~20분 늦을 수 있다.
- DART 인증키는 저장소 **Settings → Secrets → Actions** 의 `OPENDART_API_KEY` 에 넣는다.
  코드나 공개 파일에는 절대 들어가지 않는다.
