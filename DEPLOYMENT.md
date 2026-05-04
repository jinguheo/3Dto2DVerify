# Render 배포

이 저장소는 Render Web Service로 바로 배포할 수 있습니다.

## 자동 배포

1. GitHub 저장소 `https://github.com/jinguheo/3Dto2DVerify`를 Render에 연결합니다.
2. Render에서 `New > Blueprint` 또는 `New > Web Service`를 선택합니다.
3. Blueprint를 쓰는 경우 저장소 루트의 `render.yaml`을 선택합니다.
4. 수동 Web Service로 만들 경우 다음 값을 사용합니다.

```text
Language: Python
Build Command: python -m py_compile server.py
Start Command: python server.py --host 0.0.0.0 --port $PORT
Health Check Path: /health
```

배포 후 Render가 `https://3dto2dverify.onrender.com` 형태의 외부 접속 URL을 제공합니다.

## 문의 메일 알림

문의 폼은 항상 `outputs/contact_messages.jsonl`에 저장합니다. 아래 환경변수를 Render에 설정하면 저장 후 같은 내용을 메일로도 보냅니다.

```text
CONTACT_EMAIL_TO=받을 메일 주소
CONTACT_EXPORT_EMAIL_TO=문의 CSV 내보내기를 받을 메일 주소
CONTACT_EMAIL_FROM=보내는 메일 주소
ADMIN_TOKEN=문의 관리 화면에서 사용할 긴 비밀 토큰
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_STARTTLS=true
SMTP_SSL=false
SMTP_USER=SMTP 사용자
SMTP_PASSWORD=SMTP 비밀번호 또는 앱 비밀번호
```

`SMTP_HOST`와 `CONTACT_EMAIL_TO`가 없으면 메일 발송은 건너뛰고 저장만 수행합니다. Gmail을 쓰는 경우 일반 계정 비밀번호 대신 앱 비밀번호를 사용해야 합니다.

저장된 문의는 `/admin/contacts`에서 볼 수 있습니다. 화면에서 `ADMIN_TOKEN`을 입력하면 목록 조회, CSV 다운로드, CSV 메일 발송을 할 수 있습니다. 이 토큰이 없으면 문의 목록 API는 열리지 않습니다.

## 로컬 확인

```powershell
python server.py
```

브라우저에서 `http://127.0.0.1:8000`을 열어 확인합니다.
