# GitHub 업로드 가이드

## 1단계 — Git 초기화 및 첫 커밋

```bash
# 프로젝트 폴더로 이동
cd pose2sim-gui

# Git 저장소 초기화
git init

# 모든 파일 스테이징
git add .

# 첫 커밋
git commit -m "feat: initial release of Pose2Sim GUI"
```

---

## 2단계 — GitHub에 새 저장소 만들기

1. https://github.com 접속 → 로그인
2. 우측 상단 **`+`** → **New repository** 클릭
3. 아래와 같이 설정:

| 항목 | 값 |
|---|---|
| Repository name | `pose2sim-gui` |
| Description | `PyQt5 GUI for the Pose2Sim 3D motion capture pipeline` |
| Visibility | Public |
| Initialize with README | **체크 해제** (이미 있음) |
| .gitignore | **None** (이미 있음) |
| License | **None** (이미 있음) |

4. **Create repository** 클릭

---

## 3단계 — 로컬 저장소를 GitHub에 연결

GitHub가 보여주는 `…or push an existing repository` 섹션의 명령어를 그대로 사용합니다:

```bash
git remote add origin https://github.com/YOUR_USERNAME/pose2sim-gui.git
git branch -M main
git push -u origin main
```

> `YOUR_USERNAME`을 본인 GitHub 아이디로 바꾸세요.

---

## 4단계 — 확인

브라우저에서 `https://github.com/YOUR_USERNAME/pose2sim-gui` 접속 →
파일과 README가 정상적으로 보이면 완료!

---

## 이후 변경사항 업로드 방법

```bash
# 변경된 파일 확인
git status

# 변경 파일 스테이징
git add .

# 커밋 (메시지는 작업 내용에 맞게)
git commit -m "feat: add camera preview panel"

# 업로드
git push
```

---

## 자주 쓰는 커밋 메시지 컨벤션

| prefix | 용도 |
|---|---|
| `feat:` | 새 기능 추가 |
| `fix:` | 버그 수정 |
| `refactor:` | 코드 구조 개선 (기능 변경 없음) |
| `docs:` | README, 주석 등 문서 수정 |
| `style:` | UI/스타일 변경 |
| `chore:` | 빌드 설정, 의존성 업데이트 등 |
