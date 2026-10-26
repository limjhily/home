# 청약달력 (cheongyak.day)

전국 아파트 청약 정보를 날짜순으로 보여주는 정적 사이트.
매일 06:00(KST) GitHub Actions 가 데이터를 수집하고 페이지를 다시 만든다.

- 운영 주소: https://cheongyak.day
- 호스팅: Cloudflare Pages (`main` 브랜치에 push 하면 자동 배포)
- 저장소: limjhily/home

## 이 프로젝트의 핵심 차별점

**전매제한과 실거주의무(= 전세 가능 여부)를 목록에서 바로 보여준다.**

한국부동산원 청약홈 OpenAPI 에는 이 두 항목이 **들어 있지 않다.**
입주자모집공고문 PDF 안의 표에만 있다. 그래서 이 API 를 쓰는 대부분의
청약 서비스는 목록에서 이 값을 보여주지 못한다.
우리는 공고문을 파싱해서 뽑아낸다. 이게 이 사이트가 존재하는 이유다.

이 강점을 `/jeonse.html` 전용 페이지와 메인의 "전세 가능만" 필터로 노출하고 있다.

## 구조

```
index.html         메인. 스타일(<style>)은 여기 한 곳에만 있고 다른 페이지가 가져다 쓴다
jeonse.html        전세 가능 단지 모음 (자동 생성)
404.html           없는 주소용 (자동 생성). 없으면 Cloudflare 가 메인을 200 으로 내보내 soft 404 가 된다
apt/*.html         단지별 상세 페이지 (자동 생성). 접수가 끝난 단지도 "청약 마감" 표시로 계속 남긴다
privacy.html       개인정보처리방침 (수동)
contact.html       문의 (수동) · contact@cheongyak.day
data/notices.json  수집 결과 (자동 생성)
data/overrides.json  자동 추출이 틀렸을 때 손으로 덮어쓰는 값
data/pdf_cache.json  이미 읽은 공고 건너뛰기용 (자동)
data/archive.json  지금까지 나온 모든 공고 보관 (자동). 목록에서 빠진 날이 _closed
                   단지명 검색은 마감 뒤에도 들어오므로 지난 페이지를 지우지 않으려고 둔다
scripts/collect.py       청약홈 OpenAPI 수집 + 공고문에서 전매제한·거주의무 추출
scripts/pblanc_pdf.py    표(PDF·HTML 공통) 파서. --selftest 로 13종 검증
scripts/build_site.py    정적 페이지·sitemap·robots.txt 생성
scripts/probe_applyhome.py  청약홈 구조 정찰 (디버깅용)
sitemap.xml, robots.txt  자동 생성
_headers           Cloudflare Pages 캐시/보안 헤더
```

## 손대면 안 되는 곳

- `index.html` 의 `<!-- SEO:START -->` ~ `<!-- SEO:END -->` 구간 — `build_site.py` 가 덮어쓴다
- `apt/`, `jeonse.html`, `404.html`, `sitemap.xml`, `robots.txt` — 전부 자동 생성. 고치려면 `build_site.py` 를 고칠 것
- `data/notices.json`, `data/pdf_cache.json`, `data/archive.json` — 자동 생성. archive 를 지우면 지난 단지 페이지가 사라진다

## 작업 흐름

```bash
python3 scripts/collect.py --selftest      # 수집 로직 검증 (API 키 불필요)
python3 scripts/pblanc_pdf.py --selftest   # 파서 13종 검증
python3 scripts/build_site.py              # 정적 페이지 다시 만들기
python3 -m http.server 8000                # 로컬 확인 (file:// 로 열면 JSON 못 읽음)
```

`scripts/` 나 `data/overrides.json` 을 고쳐서 push 하면 수집 워크플로가 자동으로
다시 돌아 데이터와 페이지가 갱신된다. 봇이 커밋하는 파일은 트리거 목록에 없어
무한 반복은 일어나지 않는다.

## 알려진 한계

- **LH 공공분양**은 전매제한·거주의무를 못 읽는다. 청약홈에 PDF 첨부도 없고
  상세 HTML 표에도 해당 칸이 없다. 자세한 조사 내용은 README.md 참고.
  급하면 `data/overrides.json` 에 수동 입력. 현재는 "확인 필요"로 두기로 결정.
- 현재 추출률: 26건 중 23건 (88%)

## 성능·SEO 에서 주의할 점

- 폰트는 `display=optional` 이다. `swap` 으로 되돌리면 한글 폰트가 늦게 올 때
  레이아웃이 밀려 CLS 가 0.68 까지 나빠진다(측정값). 지금은 0.02.
- `.filters` 의 `min-height`, `#list` 의 `min-height` 도 같은 이유로 넣었다. 지우지 말 것.
- 구글 서치콘솔·네이버 서치어드바이저 등록 완료. 사이트맵 제출 완료.
- `index.html` 의 `naver-site-verification` 메타태그를 지우면 네이버 소유확인이 풀린다.

## 광고

애드센스 미승인 상태. `index.html` 의 `const ADS_ENABLED = false;` 를 `true` 로
바꾸면 광고 자리가 다시 나타난다. 승인 전까지 빈 점선 상자가 보이면
미완성 사이트로 보여 심사에 불리해서 꺼둔 것이다.

## 다음에 할 만한 것

1. 유입 분석 (서치콘솔 실적) 후 검색어에 맞춰 페이지 보강
2. 애드센스 신청 및 코드 삽입
3. 디자인 개선 (사용자가 한 번에 하기로 미뤄둠)
4. 실거주의무·전매제한 설명 가이드 페이지 (검색 유입 + 애드센스에 유리)
5. 관심 단지 저장 / 알림
6. 로그인 + 가점 계산·특별공급 추천 (원래 구상한 확장 방향)
