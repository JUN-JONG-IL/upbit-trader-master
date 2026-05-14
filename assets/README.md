# README: assets

CHANGELOG:
- 2026-01-31 | Copilot | 생성: assets 폴더용 README 작성. 영향: assets/upbit.svg(로고 리소스) 문서화. 테스트: 파일 존재 및 기본 내용(색상/요소) 수동 확인.

Version: v1.0  
Last Modified: 2026-01-31 | Author: Copilot  
References:
 - work_order/README_작성_가이드.md
 - work_order/규칙.md

Purpose:
assets 폴더는 애플리케이션(UI/문서/웹페이지 등)에서 사용되는 정적 리소스(이미지, 아이콘, 로고, 폰트, 기타 바이너리/텍스트 자산)를 보관하는 디렉토리입니다. 이 폴더의 파일들은 런타임 비즈니스 로직과 분리된 정적 자원으로 취급되며, 프런트엔드 표시, 문서화, 배포 패키지에 포함되는 것이 일반적입니다. assets 내 모든 파일은 프로젝트 내에서 참조 방법, 최적화 절차, 라이선스/저작권 준수 지침을 문서로 남겨야 합니다.

Note: 검색 결과는 일부일 수 있습니다. 현재 폴더의 파일 목록과 내용은 GitHub에서 직접 확인해 주세요:
https://github.com/JUN-JONG-IL/upbit-trader-master/tree/main/assets

Files:
 - upbit.svg: 프로젝트에서 사용되는 Upbit 로고(벡터 SVG 파일).

Detailed file documentation (각 파일에 대해 목적 / 사용법 / 주의사항을 상세히 기술):

1) assets/upbit.svg
 - 목적:
   - 프로젝트 UI 및 문서(README, 데모 페이지, 애플리케이션 헤더 등)에 사용되는 공식 로고(벡터 포맷). SVG이므로 해상도에 독립적이며 크기/색상 조정이 용이합니다.
 - 파일 내용 요약:
   - 이 SVG는 원(circle)과 로고 패스(path)를 포함합니다. 주요 색상으로 짙은 파란(#093687) 배경 원과 흰색(#ffffff) 로고 패스가 사용되어 있습니다. (원문 소스: assets/upbit.svg)
 - 사용법 (복사하여 바로 쓸 수 있는 예제):
   - HTML에서 이미지로 사용:
     - <img src="assets/upbit.svg" alt="Upbit logo" width="120" height="120">
   - HTML에 인라인으로 삽입(스타일·애니메이션 조작이 필요할 때):
     - 파일 내용을 복사하여 <svg>...</svg>를 직접 HTML에 붙여넣고 내부 요소에 CSS/JS로 접근 가능.
   - CSS 배경 이미지로 사용:
     - .logo { background-image: url('/assets/upbit.svg'); background-size: contain; background-repeat: no-repeat; width: 120px; height: 120px; }
   - React(또는 Vite/Webpack)에서 import하여 인라인으로 렌더링:
     - import { ReactComponent as UpbitLogo } from './assets/upbit.svg';  // CRA 설정의 경우
     - <UpbitLogo width={120} height={120} />
   - Python 애플리케이션(예: Flask)에서 정적 파일로 서빙:
     - static 폴더로 복사 후 템플릿에서: <img src="{{ url_for('static', filename='assets/upbit.svg') }}" alt="Upbit logo">
 - 권장 최적화(배포 전):
   - 벡터 파일 최적화: svgo 사용 권장
     - 설치: npm install -g svgo
     - 예: svgo assets/upbit.svg --multipass -o assets/upbit.min.svg
   - PNG/WEBP 변환(레거시 브라우저 또는 썸네일 용):
     - 예: rsvg-convert -w 200 -h 200 -o assets/upbit-200.png assets/upbit.svg
     - 또는 ImageMagick: convert -density 300 assets/upbit.svg -quality 90 assets/upbit.png
   - 자동화: CI 파이프라인에서 svgo를 실행하도록 하여 커밋 전 자동 최적화/검증 권장.
 - 접근성(Accessibility) 권장 사항:
   - <img> 사용 시 반드시 alt 속성 제공: alt="Upbit logo" 또는 alt=""(만약 장식용이라면 빈 alt와 aria-hidden="true" 사용).
   - 인라인 SVG 사용 시 <title> 및 <desc> 요소 추가하여 스크린리더 지원 강화.
 - 주의사항 / 법적·브랜딩 관련:
   - 로고 사용은 브랜드 가이드라인과 저작권/상표권에 따라 제한될 수 있습니다. 이 리포지토리에서 사용 중인 로고가 제3자 로고(예: Upbit 공식 로고)라면 상업적 사용, 변형, 재배포 관련 정책을 반드시 확인하세요.
   - 로고 색상·비율을 임의로 변경하면 브랜드 규정 위반이 될 수 있습니다. 가능하면 원본 색상 및 비율을 유지하거나 브랜드 가이드라인에 따르세요.
 - 보안 / 민감정보 관련:
   - SVG 내부에 외부 스크립트 또는 외부 리소스(URL)를 포함시키지 마세요. SVG에 포함된 <script> 또는 외부 폰트 로드(URL)는 XSS 공격 벡터가 될 수 있습니다. (현재 파일은 단순한 도형/패스만 포함됨.)
 - 버전 관리 / 파일명 규칙:
   - 리소스는 명확한 네이밍 규칙을 따르세요: {resource-kind}/{name}.{format} 또는 assets/{name}.{format}.
   - 변경 시 CHANGELOG에 변경 이유와 시안을 기록하고, 기존 클라이언트(앱)에서 의존하는 로고 규격(예: 크기, 배경 유무)이 있다면 하위 호환을 유지하세요.
 - 테스트 / 확인 항목(배포 전 체크리스트):
   - svgo 최적화 후 렌더링(브라우저) 확인: 주요 브라우저(Chrome, Firefox, Safari)에서 정상 노출 확인.
   - 파일 크기(바이트) 확인: 웹에서 로드 성능에 영향주는 경우 rasterized 아이콘 추가 제공 고려.
   - 접근성: alt/title/desc 유무 확인.
   - 라이선스: 사용 권한/출처 문서화.

Repository integration notes (애플리케이션 내 통합 가이드):
 - 웹(프론트엔드): assets 폴더를 정적 서빙 디렉토리(static, public 등)로 연결. 빌드 도구(webpack, vite, parcel)는 상대경로를 요구하므로 빌드 구성에 맞춰 경로 표준화.
 - 백엔드(문서, 이메일 템플릿): 이메일 등 외부로 보낼 때는 외부 URL(예: CDN)에 업로드된 rasterized 버전(PNG/WebP)을 사용하여 호환성 확보.
 - 배포: CDN 캐싱(버전 해시를 파일명에 포함) 정책 권장(ex: upbit.12345.svg) — 캐시 무효화 시 편리.

CI / 자동화 권장 작업:
 - pre-commit 훅: SVG 파일 변경 시 svgo 자동 실행 및 형식 검사 도구 추가(예: pre-commit hook).
 - CI 파이프라인: assets 최적화 확인 단계(예: svgo --check), 용량 임계값을 초과하면 빌드 실패 설정 검토.
 - docs/previous_stages: 중요한 자산(로고 변경 등)은 변경 전후를 docs/previous_stages에 보관하고 work_order/규칙.md에 변경 기록 추가.

Troubleshooting (자주 발생하는 문제 및 해결법)
 - 문제: SVG가 일부 브라우저에서 깨져 보임.
   - 원인/해결: 인라인에 외부 폰트/스크립트 참조가 있는지 확인, viewBox 속성 유무 확인, svgo가 제거한 속성(예: width/height)로 레이아웃이 깨졌는지 확인.
 - 문제: CI 빌드 후 아이콘이 보이지 않음.
   - 원인/해결: 빌드 도구의 asset loader가 SVG를 처리하는 방식(인라인 vs 파일출력)을 확인하고, 소스 경로가 올바른지 점검.
 - 문제: 로고 크롭/여백 문제.
   - 원인/해결: SVG 내부 viewBox와 실제 도형 경계가 일치하는지 확인. 필요 시 viewBox를 조정하거나 배경 패딩용 그룹 요소 추가.

Maintenance (유지보수 권장 절차)
 - 로고/아이콘 변경 시:
   - 변경 이유(브랜드 변경, 색상 수정 등) 문서화.
   - 이전 버전 보관(예: assets/previous/upbit-v1.svg) 및 work_order/규칙.md 또는 docs/previous_stages에 변경 로그 추가.
   - 배포 전 모든 UI(웹/앱/문서)에서 시각적 영향 검증.
 - 신규 아이콘 추가 시:
   - 파일명 규칙 준수, svgo 최적화, 접근성 태그(alt/title) 적용, 사용 예시(HTML/React/Flask 등) README에 추가.

Last Modified: 2026-01-31 | Author: Copilot
