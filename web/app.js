const rowsEl = document.querySelector("#dimensionRows");
const verifyForm = document.querySelector("#verifyForm");
const jsonView = document.querySelector("#jsonView");
const resultList = document.querySelector("#resultList");
const summaryGrid = document.querySelector("#summaryGrid");
const overallBadge = document.querySelector("#overallBadge");
const serviceStatus = document.querySelector("#serviceStatus");
const contactForm = document.querySelector("#contactForm");
const contactResult = document.querySelector("#contactResult");

const sampleRows = [
  { id: "top_hole_01", expected_mm: 5.0, measured_mm: 4.987, tolerance_mm: 0.05 },
  { id: "mount_slot_02", expected_mm: 18.5, measured_mm: 18.541, tolerance_mm: 0.05 },
  { id: "edge_width_03", expected_mm: 42.0, measured_mm: 42.063, tolerance_mm: 0.05 },
];

let dimensions = structuredClone(sampleRows);

function formatNumber(value) {
  return Number(value).toFixed(3);
}

function escapeAttribute(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderRows() {
  rowsEl.innerHTML = "";
  dimensions.forEach((row, index) => {
    const el = document.createElement("div");
    el.className = "dimension-row";
    el.innerHTML = `
      <label aria-label="검사 항목 ${index + 1}">
        <input value="${escapeAttribute(row.id)}" data-index="${index}" data-field="id" />
      </label>
      <label aria-label="기준 치수 ${index + 1}">
        <input type="number" step="0.001" value="${formatNumber(row.expected_mm)}" data-index="${index}" data-field="expected_mm" />
      </label>
      <label aria-label="측정 치수 ${index + 1}">
        <input type="number" step="0.001" value="${formatNumber(row.measured_mm)}" data-index="${index}" data-field="measured_mm" />
      </label>
      <label aria-label="공차 ${index + 1}">
        <input type="number" min="0.001" step="0.001" value="${formatNumber(row.tolerance_mm)}" data-index="${index}" data-field="tolerance_mm" />
      </label>
    `;
    rowsEl.appendChild(el);
  });
}

function syncDimensionsFromInputs() {
  rowsEl.querySelectorAll("input").forEach((input) => {
    const index = Number(input.dataset.index);
    const field = input.dataset.field;
    dimensions[index][field] = field === "id" ? input.value.trim() : Number(input.value);
  });
}

function buildPayload() {
  syncDimensionsFromInputs();
  return {
    part_id: document.querySelector("#partId").value.trim() || "PART-DEMO-001",
    tolerance_mm: Number(document.querySelector("#tolerance").value) || 0.05,
    primitives: dimensions.map((row) => ({
      id: row.id || "feature",
      type: "dimension",
      expected_mm: Number(row.expected_mm),
      measured_mm: Number(row.measured_mm),
      tolerance_mm: Number(row.tolerance_mm),
    })),
  };
}

function renderReport(report) {
  const verdictClass = report.overall.toLowerCase();
  overallBadge.textContent = report.overall;
  overallBadge.className = `verdict-badge ${verdictClass}`;

  const cells = [
    ["total", "Total"],
    ["pass", "Pass"],
    ["warning", "Warning"],
    ["fail", "Fail"],
  ];
  summaryGrid.innerHTML = cells
    .map(([key, label]) => `<div><strong>${report.summary[key]}</strong><span>${label}</span></div>`)
    .join("");

  resultList.innerHTML = report.primitives
    .map((item) => {
      const klass = item.verdict.toLowerCase();
      const sign = item.error_mm > 0 ? "+" : "";
      return `
        <div class="result-item ${klass}">
          <div>
            <strong>${item.id}</strong>
            <span>기준 ${item.expected_mm}mm / 측정 ${item.measured_mm}mm / 공차 ±${item.tolerance_mm}mm</span>
          </div>
          <em>${item.verdict} ${sign}${item.error_mm}mm</em>
        </div>
      `;
    })
    .join("");

  jsonView.textContent = JSON.stringify(report, null, 2);
}

async function runVerification() {
  const response = await fetch("/api/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildPayload()),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.message || "검증 요청 실패");
  }
  renderReport(body);
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

document.querySelector("#sampleButton").addEventListener("click", async () => {
  dimensions = structuredClone(sampleRows);
  document.querySelector("#partId").value = "PART-DEMO-001";
  document.querySelector("#tolerance").value = "0.050";
  renderRows();
  await runVerification();
});

document.querySelector("#addRowButton").addEventListener("click", () => {
  syncDimensionsFromInputs();
  dimensions.push({
    id: `feature_${dimensions.length + 1}`,
    expected_mm: 10,
    measured_mm: 10,
    tolerance_mm: Number(document.querySelector("#tolerance").value) || 0.05,
  });
  renderRows();
});

verifyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await runVerification();
  } catch (error) {
    jsonView.textContent = JSON.stringify({ error: error.message }, null, 2);
    overallBadge.textContent = "오류";
    overallBadge.className = "verdict-badge fail";
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

renderRows();
checkHealth();
runVerification().catch((error) => {
  jsonView.textContent = JSON.stringify({ error: error.message }, null, 2);
});
