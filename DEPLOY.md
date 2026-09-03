# 배포 · 운영 가이드

## 1. Cloudflare Pages 연결 (무료)

Cloudflare 계정 로그인이 필요해서 아래는 직접 하셔야 합니다. 5분이면 끝납니다.

1. https://dash.cloudflare.com 접속 → 가입/로그인
2. 왼쪽 메뉴 **Workers & Pages** → **Create** → **Pages** 탭 → **Connect to Git**
3. GitHub 계정 연결 → `limjhily/home` 저장소 선택
4. 빌드 설정 (중요 — 여기서 실수가 잦습니다)
   - Production branch: `main`
   - Framework preset: **None**
   - Build command: **비워둠**
   - Build output directory: **`/`** (또는 비워둠)
5. **Save and Deploy** → 1분 뒤 `https://<프로젝트명>.pages.dev` 주소가 나옵니다

이후 `main` 브랜치에 push할 때마다 자동으로 다시 배포됩니다.

### 내 도메인 붙이기
1. 도메인을 산다 (가비아·후이즈 등). 추천: `cheongyak.day`, `cyday.kr`
2. Cloudflare 대시보드 → **Add a site** → 도메인 입력 → Free 플랜
3. 등록기관(가비아 등) 관리 화면에서 **네임서버를 Cloudflare가 알려준 2개로 변경**
4. Pages 프로젝트 → **Custom domains** → **Set up a domain** → 내 도메인 입력
5. HTTPS 인증서는 자동 발급됩니다 (몇 분~수십 분)

---

## 2. 청약 데이터 자동 수집

### 서비스키 발급
1. https://www.data.go.kr 회원가입
2. **"한국부동산원_청약홈 분양정보 조회 서비스"** 검색 → **활용신청**
   (자동 승인, 보통 1시간 내 사용 가능)
3. 마이페이지 → 개발계정 → **일반 인증키(Decoding)** 복사

### GitHub에 키 등록
`limjhily/home` 저장소 → **Settings** → **Secrets and variables** → **Actions**
→ **New repository secret**
- Name: `DATA_GO_KR_KEY`
- Secret: 복사한 디코딩 인증키

### 동작
- `.github/workflows/collect.yml` 이 **매일 오전 6시(KST)** 실행됩니다
- 결과가 `data/notices.json` 으로 커밋되고, Cloudflare Pages가 자동 재배포합니다
- 지금 바로 돌려보려면: 저장소 **Actions** 탭 → "청약 데이터 수집" → **Run workflow**

### 손으로 확인할 것
전매제한 기간과 실거주의무는 **이 API에 들어있지 않습니다.**
수집된 항목은 사이트에 "확인 필요"로 표시되며, `data/overrides.json` 에
단지명을 키로 값을 적어두면 그 값이 우선 적용됩니다.

```json
{
  "위례 리버센트 아이파크": { "resale": 36, "live": 2 }
}
```

> API 응답의 필드명이 개편되면 수집이 비어 나올 수 있습니다.
> 그럴 땐 `python3 scripts/collect.py --debug` 로 실제 필드명을 확인하고
> `scripts/collect.py` 의 `build()` 함수 매핑을 고치면 됩니다.

---

## 3. 구글 애드센스

승인 전 필요한 것: **자체 도메인 + 실제 콘텐츠 + 개인정보처리방침 + 문의 수단**.
샘플 데이터 상태로는 승인되지 않습니다. 데이터 수집이 돌기 시작한 뒤 신청하세요.

승인 후에는 `index.html` 의 아래 두 자리에 애드센스 코드를 넣으면 됩니다.
- 상단 배너: `<div class="ad ad-top">` 를 `<ins class="adsbygoogle">` 로 교체
- 인피드: JS의 `ad.className = "ad ad-infeed"` 부분

---

## 로컬에서 확인하기

```bash
python3 -m http.server 8000
# 브라우저에서 http://localhost:8000
```

`file://` 로 직접 열면 브라우저 보안 정책 때문에 `data/notices.json` 을 못 읽고
파일 안의 샘플 데이터로 표시됩니다. 반드시 위처럼 서버로 띄우세요.
