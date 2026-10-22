# 서울 데이트메이트

이 작업 폴더에는 데이트 일정 추천 웹사이트 `datemate` 프로젝트가 있습니다.

## 실행 (PowerShell)

```powershell
cd C:\Users\SSAFY\Desktop\streamlit_lab\datemate
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

접속: http://127.0.0.1:8000

- [환경 준비·데이터·기능·검증 안내](datemate/README.md)
- 실제 API 키: `datemate/.env` (외부 공유 및 Git 등록 금지)
- 키 없는 설정 양식: `datemate/.env.example`
- Python 가상환경: `datemate/.venv`

웹사이트에서 사용하지 않는 상위 Streamlit 실습 파일과 중복 가상환경은 정리했습니다. [삭제 기록](datemate/docs/workspace-cleanup.json)
