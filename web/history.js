const adminToken = document.querySelector("#adminToken");
const historyLimit = document.querySelector("#historyLimit");
const loadHistory = document.querySelector("#loadHistory");
const historyBody = document.querySelector("#historyBody");
const adminResult = document.querySelector("#adminResult");
const adminStatus = document.querySelector("#adminStatus");

function setResult(message, ok = true) {
  adminResult.textContent = message;
  adminStatus.textContent = ok ? "관리자 연결됨" : "확인 필요";
  adminStatus.classList.toggle("ok", ok);
  adminStatus.classList.toggle("error", !ok);
}

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

loadHistory.addEventListener("click", async () => {
  setResult("불러오는 중...");
  const limit = Math.min(Math.max(Number(historyLimit.value) || 100, 1), 1000);
  
  try {
    const response = await fetch(`/api/admin/inspections?limit=${limit}`, {
      headers: { "X-Admin-Token": adminToken.value }
    });
    
    if (!response.ok) {
      const body = await response.json();
      throw new Error(body.message || "요청 실패");
    }
    
    const data = await response.json();
    renderHistory(data.inspections);
    setResult(`최근 ${data.count}건의 검사 이력을 가져왔습니다.`);
  } catch (error) {
    historyBody.innerHTML = `<tr><td colspan="5" style="color:red">${escapeHtml(error.message)}</td></tr>`;
    setResult(error.message, false);
  }
});

function renderHistory(inspections) {
  if (!inspections.length) {
    historyBody.innerHTML = '<tr><td colspan="5">검사 이력이 없습니다.</td></tr>';
    return;
  }

  historyBody.innerHTML = inspections
    .map(
      (item) => {
        const summary = `${item.pass_count} / ${item.warning_count} / ${item.fail_count}`;
        const verdictClass = item.overall.toLowerCase();
        return `
          <tr>
            <td>${escapeHtml(item.timestamp)}</td>
            <td><strong>${escapeHtml(item.part_id)}</strong></td>
            <td><span class="verdict-badge ${verdictClass}">${escapeHtml(item.overall)}</span></td>
            <td>${escapeHtml(summary)}</td>
            <td style="font-family:monospace; font-size:0.85em;">${escapeHtml(item.id)}</td>
          </tr>
        `;
      }
    )
    .join("");
}