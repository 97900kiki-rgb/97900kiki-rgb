# AI 패션 코디네이터

> 나만의 옷장과 상황에 맞는 코디를 기록하고 추천받는 정적 웹앱

**Version: `v1.1.0`**

AI 패션 코디네이터는 패션 고민을 줄여주는 AI 스타일리스트 콘셉트의 웹앱입니다. 랜딩 페이지에서 코디를 등록하고, 브라우저에 저장된 기록을 바탕으로 추천 카드를 확인할 수 있습니다.

## 주요 기능

- AI 패션 서비스 소개 및 반응형 랜딩 페이지
- 코디 사진 업로드 및 이미지 미리보기
- 코디 이름, 카테고리, 상황, 무드, 메모 등록
- 브라우저 `localStorage` 기반 나만의 룩북 저장 및 삭제
- 저장한 코디와 기본 스타일 이미지를 활용한 추천 카드 생성
- Zara 여성 재킷 카테고리로 연결되는 쇼핑 링크
- Google Gemini API 기반 실시간 스타일 상담 페이지
- 모바일 메뉴, 스크롤 리빌 애니메이션, 상세 이미지 모달

## 빠른 실행

별도 빌드 도구나 서버 설치 없이 정적 파일로 실행할 수 있습니다.

```powershell
python -m http.server 8000
```

브라우저에서 아래 주소를 엽니다.

- 메인 앱: https://fashion5.kdt2025.com/
- AI 상담: <http://localhost:8000/chat.html>
- 스타일 가이드: <http://localhost:8000/style-guide.html>

## 프로젝트 구조

```text
index.html          메인 랜딩 및 코디 등록/추천 화면
chat.html           Gemini 기반 AI 스타일 상담 화면
style-guide.html    5분 스타일 가이드
css/style.css       공통 스타일 및 컴포넌트 스타일
js/main.js          메뉴, 룩북, 추천, 모달 인터랙션
js/chat.js          Gemini API 상담 로직
images/             히어로, 기능, 코디 이미지
videos/             소개 영상 콘텐츠
```

## 배포

GitHub Pages 또는 다른 정적 웹 호스팅에 저장소 루트 디렉터리를 배포할 수 있습니다.

1. GitHub 저장소의 **Settings > Pages**로 이동합니다.
2. Source를 `Deploy from a branch`로 선택합니다.
3. Branch를 `main`, 폴더를 `/ (root)`로 지정합니다.
4. 저장 후 생성된 Pages URL에서 `index.html`을 확인합니다.

저장소: <https://github.com/97900kiki-rgb/97900kiki-rgb>

## 데이터 및 보안 안내

- 등록한 코디는 현재 브라우저의 `localStorage`에만 저장됩니다.
- 브라우저나 기기를 바꾸면 저장된 코디가 공유되지 않습니다.
- Gemini API 키도 브라우저의 `localStorage`에 저장되며, 별도 백엔드에는 저장하지 않습니다.
- 공개 배포 시 브라우저에 입력한 API 키가 노출될 수 있으므로 테스트용 키 사용을 권장합니다.
- 로그인, 서버 데이터베이스, 사용자 간 데이터 공유 기능은 포함되어 있지 않습니다.

## 외부 링크

- [Zara 여성 재킷](https://www.zara.com/kr/ko/woman-jackets-l1114.html?v1=2417772)
