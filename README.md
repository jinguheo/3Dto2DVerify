# 3Dto2DVerify

3Dto2DVerify는 3D CAD 기준과 2D 카메라 측정값을 비교해 부품 치수를 자동 판정하는 검증 서비스입니다.

현재 저장소는 웹 콘솔, JSON API, 샘플 기술 흐름 이미지, PDF 자료를 포함합니다. 외부 패키지 없이 Python 표준 라이브러리만으로 실행됩니다.

## 실행

```powershell
python server.py
```

브라우저에서 `http://127.0.0.1:8000`을 열면 웹 콘솔을 볼 수 있습니다.

공장 내부망 등 다른 장비에서 접근해야 하면 다음처럼 실행합니다.

```powershell
python server.py --host 0.0.0.0 --port 8000
```

## 제공 기능

- 웹 콘솔: 치수 항목을 입력하고 Pass, Warning, Fail 결과 확인
- 검증 API: `POST /api/verify`
- 서비스 상태 확인: `GET /health`
- 샘플 리포트: `GET /api/sample-report`
- 서비스 메타데이터: `GET /api/overview`
- 문의 저장: `POST /api/contact`

문의 데이터는 `outputs/contact_messages.jsonl`에 저장됩니다. `outputs/`는 `.gitignore`에 포함되어 있어 운영 로그가 Git에 올라가지 않습니다.

## 외부 배포

Render 배포 설정은 `render.yaml`에 들어 있습니다.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/jinguheo/3Dto2DVerify)

1. GitHub 저장소를 Render에 연결합니다.
2. `New > Blueprint`를 선택하고 이 저장소를 고릅니다.
3. Render가 `render.yaml`을 읽어 Python Web Service를 생성합니다.

수동 Web Service로 만들 경우:

```text
Build Command: python -m py_compile server.py
Start Command: python server.py --host 0.0.0.0 --port $PORT
Health Check Path: /health
```

자세한 내용은 `DEPLOYMENT.md`를 참고하세요.

## 검증 API 예시

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/verify `
  -ContentType "application/json" `
  -Body '{
    "part_id": "PART-2026-001",
    "tolerance_mm": 0.05,
    "primitives": [
      { "id": "hole_1", "expected_mm": 5.000, "measured_mm": 4.987, "tolerance_mm": 0.050 },
      { "id": "slot_1", "expected_mm": 18.500, "measured_mm": 18.541, "tolerance_mm": 0.050 }
    ]
  }'
```

응답은 다음 형태입니다.

```json
{
  "inspection_id": "INSP-XXXXXXXXXX",
  "part_id": "PART-2026-001",
  "timestamp": "2026-05-01T00:00:00Z",
  "overall": "WARNING",
  "summary": { "total": 2, "pass": 1, "warning": 1, "fail": 0 },
  "primitives": [
    {
      "id": "hole_1",
      "type": "dimension",
      "verdict": "PASS",
      "expected_mm": 5.0,
      "measured_mm": 4.987,
      "error_mm": -0.013,
      "abs_error_mm": 0.013,
      "tolerance_mm": 0.05
    }
  ]
}
```

## 프로젝트 구조

```text
.
├── server.py
├── web/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── tech_overview.png
├── Autonomous 4K Metrology Solution.pdf
├── docs/
│   └── concept.md
└── outputs/
```

## 다음 개발 후보

- 실제 STEP/IGES/DXF 파서 연결
- 카메라 이미지 업로드와 캘리브레이션 결과 저장
- PDF 리포트 자동 생성
- 사용자 인증과 프로젝트별 검사 이력 관리
- MES/ERP Webhook 또는 OPC UA 연동
