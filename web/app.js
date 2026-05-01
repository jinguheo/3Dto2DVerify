const serviceStatus = document.querySelector("#serviceStatus");
const contactForm = document.querySelector("#contactForm");
const contactResult = document.querySelector("#contactResult");
const overviewFrame = document.querySelector("#overviewFrame");
const scanWindow = document.querySelector("#scanWindow");
const focusMarker = document.querySelector("#focusMarker");
const stepStrip = document.querySelector("#stepStrip");
const playDemoButton = document.querySelector("#playDemoButton");
const demoLaneBadge = document.querySelector("#demoLaneBadge");
const demoStepTitle = document.querySelector("#demoStepTitle");
const demoStepBody = document.querySelector("#demoStepBody");
const demoProgressBar = document.querySelector("#demoProgressBar");
const inspectionMetrics = document.querySelector("#inspectionMetrics");
const overallBadge = document.querySelector("#overallBadge");
const jsonView = document.querySelector("#jsonView");

const demoSteps = [
  {
    lane: "Top View Lane",
    shortLane: "Top",
    title: "Target Model",
    body: "상면 CAD 기준 모델을 불러와 카메라 이미지와 비교할 기준 좌표계를 준비합니다.",
    x: 1.8,
    y: 18.5,
    w: 13,
    h: 19,
  },
  {
    lane: "Top View Lane",
    shortLane: "Top",
    title: "Camera Input",
    body: "상면 카메라 입력 이미지를 수집하고 조명 상태와 선명도를 확인합니다.",
    x: 15.5,
    y: 18.5,
    w: 12.5,
    h: 19,
  },
  {
    lane: "Top View Lane",
    shortLane: "Top",
    title: "Calibration",
    body: "픽셀 좌표를 mm 단위로 변환하기 위해 카메라 캘리브레이션을 적용합니다.",
    x: 29,
    y: 18.5,
    w: 12.6,
    h: 19,
  },
  {
    lane: "Top View Lane",
    shortLane: "Top",
    title: "Crop & Target",
    body: "상면 보드 영역을 잘라내고 CAD 투영 기준 이미지를 검사 타깃으로 정렬합니다.",
    x: 43.2,
    y: 18.5,
    w: 26.2,
    h: 19,
  },
  {
    lane: "Top View Lane",
    shortLane: "Top",
    title: "Edge & Compare",
    body: "윤곽선을 추출해 상면 CAD 기준과 실제 촬영 결과의 형상 차이를 비교합니다.",
    x: 70.8,
    y: 18.5,
    w: 27,
    h: 19,
    payload: {
      part_id: "TOP-LANE-DEMO",
      tolerance_mm: 0.05,
      primitives: [
        { id: "top_hole_01", expected_mm: 5.0, measured_mm: 4.987, tolerance_mm: 0.05 },
        { id: "top_slot_02", expected_mm: 18.5, measured_mm: 18.541, tolerance_mm: 0.05 },
      ],
    },
  },
  {
    lane: "Bottom View Lane",
    shortLane: "Bottom",
    title: "Target Model",
    body: "하면 CAD 기준 모델을 별도 레인으로 불러와 양면 검증 기준을 분리합니다.",
    x: 1.8,
    y: 55.2,
    w: 12.8,
    h: 18.5,
  },
  {
    lane: "Bottom View Lane",
    shortLane: "Bottom",
    title: "Camera & Calibration",
    body: "하면 카메라 이미지에 캘리브레이션을 적용해 라인별 측정 기준을 통일합니다.",
    x: 15.4,
    y: 55.2,
    w: 25.8,
    h: 18.5,
  },
  {
    lane: "Bottom View Lane",
    shortLane: "Bottom",
    title: "Alignment & Crop",
    body: "하면 이미지를 회전, 이동, 크롭해 CAD 기준 위치에 맞춥니다.",
    x: 42.8,
    y: 55.2,
    w: 26.2,
    h: 18.5,
  },
  {
    lane: "Bottom View Lane",
    shortLane: "Bottom",
    title: "Overlay & Vector",
    body: "오버레이와 벡터 윤곽을 생성해 하단 형상 차이를 구조화된 데이터로 변환합니다.",
    x: 70.8,
    y: 55.2,
    w: 27.2,
    h: 18.5,
    payload: {
      part_id: "BOTTOM-LANE-DEMO",
      tolerance_mm: 0.05,
      primitives: [
        { id: "bottom_boss_01", expected_mm: 12.0, measured_mm: 11.982, tolerance_mm: 0.05 },
        { id: "bottom_edge_02", expected_mm: 42.0, measured_mm: 42.063, tolerance_mm: 0.05 },
      ],
    },
  },
  {
    lane: "Auto Model Checker",
    shortLane: "Checker",
    title: "Final Geometry Review",
    body: "상면과 하면 검사 결과를 통합해 최종 형상 일치 여부와 Pass/Warning/Fail 리포트를 생성합니다.",
    x: 1.8,
    y: 84.5,
    w: 16.5,
    h: 12.4,
    payload: {
      part_id: "FULL-MODEL-CHECKER",
      tolerance_mm: 0.05,
      primitives: [
        { id: "top_hole_01", expected_mm: 5.0, measured_mm: 4.987, tolerance_mm: 0.05 },
        { id: "top_slot_02", expected_mm: 18.5, measured_mm: 18.541, tolerance_mm: 0.05 },
        { id: "bottom_edge_02", expected_mm: 42.0, measured_mm: 42.063, tolerance_mm: 0.05 },
      ],
    },
  },
];

let activeStepIndex = 0;
let demoTimer = null;

function setCssPercent(element, name, value) {
  element.style.setProperty(name, `${value}%`);
}

function fallbackReport(step) {
  return {
    part_id: step.payload?.part_id || "TECH-OVERVIEW-DEMO",
    overall: "READY",
    summary: { total: 0, pass: 0, warning: 0, fail: 0 },
    primitives: [],
  };
}

async function requestReport(step) {
  if (!step.payload) {
    return fallbackReport(step);
  }

  const response = await fetch("/api/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(step.payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.message || "검증 요청 실패");
  }
  return body;
}

function renderStepButtons() {
  stepStrip.innerHTML = demoSteps
    .map(
      (step, index) => `
        <button type="button" class="step-button" data-step="${index}">
          <span>${step.shortLane}</span>
          ${String(index + 1).padStart(2, "0")} ${step.title}
        </button>
      `,
    )
    .join("");

  stepStrip.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      stopDemoPlayback();
      showDemoStep(Number(button.dataset.step));
    });
  });
}

function renderMetrics(report, step) {
  const topStatus = activeStepIndex >= 4 ? "Edge 비교 완료" : step.shortLane === "Top" ? "처리 중" : "대기";
  const bottomStatus = activeStepIndex >= 8 ? "Vector 생성 완료" : step.shortLane === "Bottom" ? "처리 중" : "대기";
  const checkerStatus = report.overall === "READY" ? "대기" : report.overall;

  inspectionMetrics.innerHTML = `
    <div><strong>Top</strong><span>${topStatus}</span></div>
    <div><strong>Bottom</strong><span>${bottomStatus}</span></div>
    <div><strong>Checker</strong><span>${checkerStatus}</span></div>
  `;
}

function renderReport(report) {
  const verdict = report.overall || "READY";
  overallBadge.textContent = verdict === "READY" ? "대기" : verdict;
  overallBadge.className = `verdict-badge ${verdict.toLowerCase()}`;
  jsonView.textContent = JSON.stringify(report, null, 2);
}

async function showDemoStep(index) {
  activeStepIndex = (index + demoSteps.length) % demoSteps.length;
  const step = demoSteps[activeStepIndex];
  const progress = ((activeStepIndex + 1) / demoSteps.length) * 100;

  setCssPercent(overviewFrame, "--scan-x", step.x);
  setCssPercent(overviewFrame, "--scan-y", step.y);
  setCssPercent(overviewFrame, "--scan-w", step.w);
  setCssPercent(overviewFrame, "--scan-h", step.h);
  setCssPercent(overviewFrame, "--marker-x", step.x + Math.min(step.w - 1, 3));
  setCssPercent(overviewFrame, "--marker-y", step.y + Math.min(step.h - 1, 4));
  setCssPercent(demoProgressBar, "--progress", progress);

  demoLaneBadge.textContent = step.lane;
  demoStepTitle.textContent = step.title;
  demoStepBody.textContent = step.body;

  stepStrip.querySelectorAll("button").forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.step) === activeStepIndex);
  });

  try {
    const report = await requestReport(step);
    renderMetrics(report, step);
    renderReport(report);
  } catch (error) {
    const report = {
      error: error.message,
      part_id: step.payload?.part_id || "TECH-OVERVIEW-DEMO",
      overall: "FAIL",
    };
    renderMetrics(report, step);
    renderReport(report);
  }
}

function stopDemoPlayback() {
  if (demoTimer) {
    clearInterval(demoTimer);
    demoTimer = null;
  }
  playDemoButton.textContent = "자동 재생";
}

function startDemoPlayback() {
  showDemoStep(activeStepIndex + 1);
  demoTimer = setInterval(() => {
    showDemoStep(activeStepIndex + 1);
  }, 1800);
  playDemoButton.textContent = "일시 정지";
}

async function checkHealth() {
  try {
    const response = await fetch("/health");
    const body = await response.json();
    serviceStatus.textContent = body.status === "ok" ? "데모 서버 정상" : "상태 이상";
    serviceStatus.className = `status-pill ${body.status === "ok" ? "ok" : "error"}`;
  } catch {
    serviceStatus.textContent = "데모 서버 연결 실패";
    serviceStatus.className = "status-pill error";
  }
}

playDemoButton.addEventListener("click", () => {
  if (demoTimer) {
    stopDemoPlayback();
  } else {
    startDemoPlayback();
  }
});

contactForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  contactResult.textContent = "저장 중입니다.";
  try {
    const response = await fetch("/api/contact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: document.querySelector("#contactName").value,
        email: document.querySelector("#contactEmail").value,
        company: document.querySelector("#contactCompany").value,
        message: document.querySelector("#contactMessage").value,
      }),
    });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.message || "문의 저장 실패");
    }
    contactResult.textContent = `저장되었습니다. 문의 ID: ${body.message_id}`;
    contactForm.reset();
  } catch (error) {
    contactResult.textContent = error.message;
  }
});

renderStepButtons();
checkHealth();
showDemoStep(0);
