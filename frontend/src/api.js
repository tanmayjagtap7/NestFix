const BASE = import.meta.env.VITE_API_URL ?? "";

export function money(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export function plainTalk(value) {
  return String(value || "")
    .replace(/sticker price/gi, "listed rent")
    .replace(/\bsticker\b/gi, "listed rent");
}

export function bedsLabel(value) {
  if (value === null || value === undefined) return "Beds n/a";
  if (Number(value) === 0) return "Studio";
  const n = Number(value);
  const shown = Number.isInteger(n) ? n : n;
  return `${shown} ${shown === 1 ? "bedroom" : "bedrooms"}`;
}

function readableError(message) {
  const text = String(message || "");
  if (text.includes("high demand") || text.includes("UNAVAILABLE") || text.includes('"code": 503')) {
    return "Search is busy right now. Try again in a moment.";
  }
  if (text.trim().startsWith("{") || text.includes('"error"')) {
    return "Something went wrong. Try again.";
  }
  return text;
}

async function parse(response) {
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = data && data.detail;
    const raw = typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : response.statusText;
    throw new Error(readableError(raw));
  }
  return data;
}

export function api(path, options = {}) {
  const headers = {
    "ngrok-skip-browser-warning": "1",
    ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers || {}),
  };
  return fetch(`${BASE}${path}`, { ...options, headers }).then(parse);
}

export const getHealth = () => api("/health");
export const getEmployers = () => api("/employers");
export const createEmployer = (body) => api("/employers", { method: "POST", body: JSON.stringify(body) });
export const getEmployees = (employerId) => api(`/employers/${employerId}/employees`);
export const getSummary = (employerId) => api(`/employers/${employerId}/selections-summary`);
export const uploadCsv = (employerId, file) => {
  const body = new FormData();
  body.append("employer_id", String(employerId));
  body.append("file", file);
  return api("/employers/upload-employees", { method: "POST", body });
};
export const uploadJson = (payload) =>
  api("/employers/upload-employees", { method: "POST", body: JSON.stringify(payload) });
export const getOptions = (employeeId) => api(`/employees/${employeeId}/options`);
export const getEmployee = (employeeId) => api(`/employees/${employeeId}`);
export const updateEmployee = (employeeId, body) =>
  api(`/employees/${employeeId}`, { method: "PATCH", body: JSON.stringify(body) });
export const generateOptions = (employeeId) =>
  api(`/housing/generate-options/${employeeId}`, { method: "POST" });
export const selectOption = (employeeId, housingOptionId, employeeNotes) =>
  api(`/employees/${employeeId}/select-option`, {
    method: "POST",
    body: JSON.stringify({ housing_option_id: housingOptionId, employee_notes: employeeNotes || null }),
  });
export const affordability = (employeeId, body) =>
  api(`/employees/${employeeId}/affordability-calc`, { method: "POST", body: JSON.stringify(body) });
export const getLogs = (employeeId) => api(`/employees/${employeeId}/logs`);
export const getOption = (optionId) => api(`/housing/options/${optionId}`);
export const getQuestions = (optionId) => api(`/housing/options/${optionId}/questions`);
export const askAboutHome = (optionId, question) =>
  api(`/housing/options/${optionId}/ask`, { method: "POST", body: JSON.stringify({ question }) });

function csvCell(value) {
  const text = value == null ? "" : String(value);
  if (/[",\n]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

export function downloadChoices(employerName, rows) {
  const header = ["Person", "Email", "City", "Status", "Home", "Listed rent", "Company pays", "Employee pays", "Note"];
  const body = (rows || []).map((row) => [
    row.full_name,
    row.email,
    row.preferred_city,
    row.status === "selected" ? "Chosen" : "Not chosen",
    row.address || "",
    row.sticker_price ?? "",
    row.employer_monthly_cover ?? "",
    row.net_price ?? "",
    row.employee_notes || "",
  ]);
  const csv = [header, ...body].map((cols) => cols.map(csvCell).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  const slug = String(employerName || "company")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  link.download = `${slug || "company"}-choices.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
