const adminToken = document.querySelector("#adminToken");
const contactLimit = document.querySelector("#contactLimit");
const loadContacts = document.querySelector("#loadContacts");
const downloadContacts = document.querySelector("#downloadContacts");
const emailContacts = document.querySelector("#emailContacts");
const exportRecipient = document.querySelector("#exportRecipient");
const contactsBody = document.querySelector("#contactsBody");
const adminResult = document.querySelector("#adminResult");
const adminStatus = document.querySelector("#adminStatus");

function setResult(message, ok = true) {
  adminResult.textContent = message;
  adminStatus.textContent = ok ? "관리자 연결됨" : "확인 필요";
  adminStatus.classList.toggle("ok", ok);
  adminStatus.classList.toggle("error", !ok);
}

function authHeaders() {
  return {
    "X-Admin-Token": adminToken.value,
  };
}

function renderContacts(contacts) {
  if (!contacts.length) {
    contactsBody.innerHTML = '<tr><td colspan="5">저장된 문의가 없습니다.</td></tr>';
    return;
  }

  contactsBody.innerHTML = contacts
    .map(
      (contact) => `
        <tr>
          <td>${escapeHtml(contact.timestamp)}</td>
          <td>${escapeHtml(contact.name)}</td>
          <td><a href="mailto:${escapeAttribute(contact.email)}">${escapeHtml(contact.email)}</a></td>
          <td>${escapeHtml(contact.company || "-")}</td>
          <td>${escapeHtml(contact.message)}</td>
        </tr>
      `
    )
    .join("");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return encodeURIComponent(String(value ?? "").replaceAll("\n", " ").replaceAll("\r", " "));
}

async function readError(response) {
  try {
    const body = await response.json();
    return body.message || "요청 실패";
  } catch (error) {
    return "요청 실패";
  }
}

async function fetchContacts() {
  const limit = Math.min(Math.max(Number(contactLimit.value) || 200, 1), 1000);
  const response = await fetch(`/api/admin/contacts?limit=${limit}`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

loadContacts.addEventListener("click", async () => {
  setResult("목록을 불러오는 중입니다.");
  try {
    const body = await fetchContacts();
    renderContacts(body.contacts);
    setResult(`문의 ${body.returned}건 표시 중 / 전체 ${body.count}건`);
  } catch (error) {
    renderContacts([]);
    setResult(error.message, false);
  }
});

downloadContacts.addEventListener("click", async () => {
  setResult("CSV를 준비하는 중입니다.");
  try {
    const limit = Math.min(Math.max(Number(contactLimit.value) || 200, 1), 1000);
    const response = await fetch(`/api/admin/contacts?format=csv&limit=${limit}`, {
      headers: authHeaders(),
    });
    if (!response.ok) {
      throw new Error(await readError(response));
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "3dto2dverify-contacts.csv";
    link.click();
    URL.revokeObjectURL(url);
    setResult("CSV 다운로드가 준비되었습니다.");
  } catch (error) {
    setResult(error.message, false);
  }
});

emailContacts.addEventListener("click", async () => {
  const recipient = exportRecipient.value.trim();
  const targetText = recipient || "Render에 설정된 기본 수신자";
  const confirmed = window.confirm(`저장된 문의 CSV를 ${targetText}에게 메일로 보낼까요?`);
  if (!confirmed) {
    return;
  }

  setResult("메일을 발송하는 중입니다.");
  try {
    const response = await fetch("/api/admin/contacts/email", {
      method: "POST",
      headers: {
        ...authHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ recipient }),
    });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.message || "메일 발송 실패");
    }
    setResult(`${body.count}건을 ${body.recipient}에게 보냈습니다.`);
  } catch (error) {
    setResult(error.message, false);
  }
});
