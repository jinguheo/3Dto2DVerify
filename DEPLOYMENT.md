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

## 로컬 확인

```powershell
python server.py
```

브라우저에서 `http://127.0.0.1:8000`을 열어 확인합니다.
