const API_STORAGE_KEY = "docintel_api_base_url";
const API_PLACEHOLDER = "PASTE_YOUR_API_URL_HERE";

let apiBaseUrl = "";

const apiUrlInput = document.getElementById("api-url-input");
const saveApiBtn = document.getElementById("save-api-btn");
const apiOutput = document.getElementById("api-output");

const uploadForm = document.getElementById("upload-form");
const fileInput = document.getElementById("file-input");
const uploadMessage = document.getElementById("upload-message");
const uploadSelection = document.getElementById("upload-selection");
const dropZone = document.getElementById("drop-zone");
const uploadSubmitBtn = uploadForm.querySelector("button[type='submit']");
const uploadProgress = document.getElementById("upload-progress");
const uploadProgressText = document.getElementById("upload-progress-text");

const tagInput = document.getElementById("tag-input");
const listBtn = document.getElementById("list-btn");
const selectAllBtn = document.getElementById("select-all-btn");
const deleteSelectedBtn = document.getElementById("delete-selected-btn");
const resultsGrid = document.getElementById("results-grid");
const listMeta = document.getElementById("list-meta");
const listError = document.getElementById("list-error");

const docIdInput = document.getElementById("doc-id-input");
const detailBtn = document.getElementById("detail-btn");
const detailPanel = document.getElementById("detail-panel");
const detailRawWrap = document.getElementById("detail-raw-wrap");
const detailRaw = document.getElementById("detail-raw");
const detailError = document.getElementById("detail-error");
const cacheIndicator = document.getElementById("cache-indicator");
let selectedUploadFiles = [];
const pendingDocumentIds = new Set();
const selectedDocumentIds = new Set();

function fileIdentityKey(file) {
  return `${(file.name || "").toLowerCase()}|${file.size}|${file.lastModified}`;
}

function setUploadBusy(isBusy, progressText = "") {
  uploadSubmitBtn.disabled = isBusy;
  fileInput.disabled = isBusy;
  dropZone.style.pointerEvents = isBusy ? "none" : "auto";
  dropZone.textContent = isBusy ? (progressText || "Uploading...") : "Drag and drop files here";
  uploadProgress.hidden = !isBusy;
  uploadProgressText.textContent = progressText || "Uploading...";
}

function normalizeApiUrl(url) {
  return (url || "").trim().replace(/\/+$/, "");
}

function readApiUrlFromQuery() {
  const params = new URLSearchParams(window.location.search);
  return normalizeApiUrl(params.get("api") || "");
}

/** Priority: ?api= → saved URL in localStorage → config.json (deployed site). */
async function resolveApiUrl() {
  const fromQuery = readApiUrlFromQuery();
  if (fromQuery) {
    localStorage.setItem(API_STORAGE_KEY, fromQuery);
    return { url: fromQuery, source: "query" };
  }
  const fromStorage = normalizeApiUrl(localStorage.getItem(API_STORAGE_KEY) || "");
  if (fromStorage) {
    return { url: fromStorage, source: "localStorage" };
  }
  try {
    const r = await fetch("config.json", { cache: "no-store" });
    if (r.ok) {
      const cfg = await r.json();
      const u = normalizeApiUrl(cfg.apiBaseUrl || cfg.api_base_url || "");
      if (u) {
        return { url: u, source: "config.json" };
      }
    }
  } catch (_) {
    /* config missing locally or blocked — fall through */
  }
  return { url: "", source: "none" };
}

function setApiUrl(url) {
  apiBaseUrl = normalizeApiUrl(url);
}

function renderApiStatus(source) {
  if (apiBaseUrl) {
    const src =
      source === "config.json"
        ? " (from config.json)"
        : source === "localStorage"
          ? " (saved in this browser)"
          : source === "query"
            ? " (from ?api= link)"
            : "";
    apiOutput.textContent = `Connected: ${apiBaseUrl}${src}`;
  } else {
    apiOutput.textContent =
      "Enter your API Gateway base URL and click Save, or deploy the Frontend stack so config.json is present.";
  }
}

function saveApiUrl() {
  const raw = apiUrlInput.value;
  const normalized = normalizeApiUrl(raw);
  if (!normalized || normalized.includes(API_PLACEHOLDER)) {
    throw new Error("Please enter a valid API URL.");
  }
  localStorage.setItem(API_STORAGE_KEY, normalized);
  setApiUrl(normalized);
  renderApiStatus("localStorage");
}

function ensureApiConfigured() {
  if (!apiBaseUrl || apiBaseUrl.includes(API_PLACEHOLDER)) {
    throw new Error("Please set your API URL in the first section.");
  }
}

function pretty(obj) {
  return JSON.stringify(obj, null, 2);
}

function escapeHtml(s) {
  if (s == null) return "";
  const div = document.createElement("div");
  div.textContent = String(s);
  return div.innerHTML;
}

/** S3 keys look like uploads/{document_id}/filename.ext — use last segment as display name. */
function fileNameFromKey(key) {
  if (!key || typeof key !== "string") return "";
  const parts = key.split("/").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : "";
}

function displayDocumentTitle(item) {
  const name = fileNameFromKey(item.key);
  if (name) return name;
  return "Untitled document";
}

function formatFinishedTime(unixSeconds) {
  const n = Number(unixSeconds);
  if (!Number.isFinite(n) || n <= 0) return "Unknown";
  return new Date(n * 1000).toLocaleString();
}

/** PDF and .txt only — must match upload Lambda allowed types. */
function resolveUploadContentType(file) {
  const name = (file.name || "").toLowerCase();
  if (name.endsWith(".pdf")) return "application/pdf";
  if (name.endsWith(".txt")) return "text/plain";
  return null;
}

async function postJson(path, body) {
  const res = await fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = typeof data.message === "string" ? data.message : `Request failed (${res.status}). ${pretty(data)}`;
    throw new Error(msg);
  }
  return data;
}

async function getJson(path) {
  const res = await fetch(`${apiBaseUrl}${path}`, { method: "GET" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(`Request failed (${res.status}). ${pretty(data)}`);
  }
  return { data, headers: res.headers };
}

async function deleteJson(path) {
  const res = await fetch(`${apiBaseUrl}${path}`, { method: "DELETE" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = typeof data.message === "string" ? data.message : `Delete failed (${res.status}). ${pretty(data)}`;
    throw new Error(msg);
  }
  return data;
}

function updateBatchDeleteButton() {
  const count = selectedDocumentIds.size;
  deleteSelectedBtn.textContent = `Delete selected (${count})`;
  deleteSelectedBtn.disabled = count === 0;
}

function updateSelectAllButtonState() {
  const boxes = resultsGrid.querySelectorAll(".card-select");
  if (boxes.length === 0) {
    selectAllBtn.disabled = true;
    return;
  }
  selectAllBtn.disabled = false;
  let allChecked = true;
  for (const box of boxes) {
    if (!box.checked) {
      allChecked = false;
      break;
    }
  }
  selectAllBtn.textContent = allChecked ? "Deselect all" : "Select all";
}

function selectAllVisibleCards() {
  const boxes = resultsGrid.querySelectorAll(".card-select");
  if (boxes.length === 0) return;
  const allSelected = Array.from(boxes).every((b) => b.checked);
  if (allSelected) {
    for (const box of boxes) {
      box.checked = false;
      const sid = box.getAttribute("data-select-id") || "";
      if (sid) selectedDocumentIds.delete(sid);
    }
  } else {
    for (const box of boxes) {
      box.checked = true;
      const sid = box.getAttribute("data-select-id") || "";
      if (sid) selectedDocumentIds.add(sid);
    }
  }
  updateBatchDeleteButton();
  updateSelectAllButtonState();
}

function showUploadMessage(html, isError) {
  uploadMessage.hidden = false;
  uploadMessage.innerHTML = html;
  uploadMessage.style.background = isError ? "#fef2f2" : "#ecfdf5";
  uploadMessage.style.borderColor = isError ? "#fecaca" : "#a7f3d0";
  uploadMessage.style.color = isError ? "#991b1b" : "#065f46";
}

function setSelectedFiles(files) {
  const all = Array.from(files || []);
  const seen = new Set();
  const unique = [];
  let duplicateCount = 0;
  for (const f of all) {
    const key = fileIdentityKey(f);
    if (seen.has(key)) {
      duplicateCount += 1;
      continue;
    }
    seen.add(key);
    unique.push(f);
  }
  selectedUploadFiles = unique;
  if (selectedUploadFiles.length === 0) {
    uploadSelection.textContent = "No files selected.";
  } else if (selectedUploadFiles.length === 1) {
    uploadSelection.textContent = `Selected: ${selectedUploadFiles[0].name}`;
  } else {
    const names = selectedUploadFiles.map((f) => f.name);
    const preview = names.slice(0, 5).join(", ");
    const more = names.length > 5 ? ` (+${names.length - 5} more)` : "";
    uploadSelection.textContent = `Selected ${selectedUploadFiles.length} files: ${preview}${more}`;
  }
  if (duplicateCount > 0) {
    uploadSelection.textContent += ` | Skipped ${duplicateCount} duplicate file(s).`;
  }
}

async function uploadSingleFile(file) {
  const contentType = resolveUploadContentType(file);
  if (!contentType) {
    return {
      ok: false,
      fileName: file.name,
      message: "Incorrect document type. Only PDF and plain text (.txt) files are allowed.",
    };
  }

  const uploadInfo = await postJson("/upload", {
    filename: file.name,
    content_type: contentType,
  });
  if (!uploadInfo.upload_url || !uploadInfo.key) {
    throw new Error("Unexpected response from server.");
  }

  const s3Res = await fetch(uploadInfo.upload_url, {
    method: "PUT",
    headers: { "content-type": uploadInfo.content_type },
    body: file,
  });
  if (!s3Res.ok) {
    return {
      ok: false,
      fileName: file.name,
      message: `Upload to storage failed (HTTP ${s3Res.status}).`,
    };
  }
  return {
    ok: true,
    fileName: fileNameFromKey(uploadInfo.key) || file.name,
    documentId: uploadInfo.document_id || "",
  };
}

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  uploadMessage.hidden = true;
  uploadMessage.textContent = "";
  try {
    ensureApiConfigured();
    if (selectedUploadFiles.length === 0) {
      throw new Error("Choose one or more files first.");
    }

    const results = [];
    const total = selectedUploadFiles.length;
    setUploadBusy(true, `Uploading 0 / ${total}...`);
    for (let i = 0; i < selectedUploadFiles.length; i += 1) {
      const file = selectedUploadFiles[i];
      setUploadBusy(true, `Uploading ${i + 1} / ${total}: ${file.name}`);
      try {
        results.push(await uploadSingleFile(file));
      } catch (err) {
        results.push({
          ok: false,
          fileName: file.name,
          message: String(err.message || err),
        });
      }
    }

    const success = results.filter((x) => x.ok);
    const failed = results.filter((x) => !x.ok);
    const parts = [
      `<strong>Upload finished</strong> Success: ${success.length}, Failed: ${failed.length}.`,
    ];

    if (success.length > 0) {
      const okRows = success
        .map(
          (r) =>
            `- ${escapeHtml(r.fileName)} (Document ID: <span class="mono-inline">${escapeHtml(
              r.documentId
            )}</span>)`
        )
        .join("<br>");
      parts.push(`<br><br><strong>Successful uploads</strong><br>${okRows}`);
      docIdInput.value = success[0].documentId || docIdInput.value;
      for (const s of success) {
        if (s.documentId) pendingDocumentIds.add(s.documentId);
      }
    }
    if (failed.length > 0) {
      const badRows = failed
        .map((r) => `- ${escapeHtml(r.fileName)}: ${escapeHtml(r.message)}`)
        .join("<br>");
      parts.push(`<br><br><strong>Failed uploads</strong><br>${badRows}`);
    }

    showUploadMessage(parts.join(""), failed.length > 0 && success.length === 0);
  } catch (err) {
    showUploadMessage(escapeHtml(String(err.message || err)), true);
  } finally {
    setUploadBusy(false);
  }
});

fileInput.addEventListener("change", () => {
  setSelectedFiles(fileInput.files);
});

dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("active");
});
dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("active");
});
dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("active");
  const dropped = event.dataTransfer?.files || [];
  setSelectedFiles(dropped);
});

function renderResultCards(items) {
  resultsGrid.innerHTML = "";
  const visibleIds = new Set(items.map((x) => String(x.document_id || "")));
  for (const id of Array.from(selectedDocumentIds)) {
    if (!visibleIds.has(id)) selectedDocumentIds.delete(id);
  }
  updateBatchDeleteButton();
  for (const item of items) {
    const id = item.document_id || "";
    const title = displayDocumentTitle(item);
    const finishedAt = formatFinishedTime(item.created_at);
    const pending = pendingDocumentIds.has(id);
    if (pending) pendingDocumentIds.delete(id);
    const card = document.createElement("article");
    card.className = "result-card";
    card.setAttribute("role", "button");
    card.tabIndex = 0;
    const tags = Array.isArray(item.tags) ? item.tags : [];
    const tagHtml =
      tags.length > 0
        ? tags.map((t) => `<span class="tag-chip">${escapeHtml(t)}</span>`).join("")
        : `<span class="tag-chip">no tags</span>`;
    const checked = selectedDocumentIds.has(id) ? "checked" : "";
    card.innerHTML =
      `<div class="result-card__top">` +
      `<input type="checkbox" class="card-select" data-select-id="${escapeHtml(id)}" ${checked} aria-label="Select ${escapeHtml(
        title
      )}">` +
      `<div style="flex:1">` +
      `<div class="result-card__header">` +
      `<div class="result-card__title">${escapeHtml(title)}</div>` +
      `<div class="result-card__time">Finished: ${escapeHtml(finishedAt)}</div>` +
      `</div>` +
      `<div class="result-card__id" title="Document ID">${escapeHtml(id)}</div>` +
      `<div class="result-card__meta">Status: <strong>${escapeHtml(item.status || "—")}</strong>${pending ? " (just completed)" : ""}</div>` +
      `<div style="margin-top:0.4rem">${tagHtml}</div>` +
      `<div class="result-card__actions"><button type="button" class="btn-danger" data-delete-id="${escapeHtml(
        id
      )}" data-delete-name="${escapeHtml(title)}">Delete</button></div>` +
      `</div>` +
      `</div>`;
    card.addEventListener("click", () => {
      docIdInput.value = id;
      detailBtn.click();
    });
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        card.click();
      }
    });
    const selectBox = card.querySelector(".card-select");
    if (selectBox) {
      selectBox.addEventListener("click", (event) => {
        event.stopPropagation();
      });
      selectBox.addEventListener("change", () => {
        const sid = selectBox.getAttribute("data-select-id") || "";
        if (selectBox.checked) selectedDocumentIds.add(sid);
        else selectedDocumentIds.delete(sid);
        updateBatchDeleteButton();
        updateSelectAllButtonState();
      });
    }
    const deleteBtn = card.querySelector(".btn-danger");
    if (deleteBtn) {
      deleteBtn.addEventListener("click", async (event) => {
        event.stopPropagation();
        const deleteId = deleteBtn.getAttribute("data-delete-id") || "";
        const deleteName = deleteBtn.getAttribute("data-delete-name") || "this document";
        const confirmed = window.confirm(
          `Delete ${deleteName}?\nThis removes both S3 object and result metadata.`
        );
        if (!confirmed) return;
        try {
          deleteBtn.disabled = true;
          await deleteJson(`/results/${encodeURIComponent(deleteId)}`);
          listMeta.textContent = `Deleted: ${deleteName}`;
          listBtn.click();
        } catch (err) {
          listError.textContent = String(err.message || err);
          deleteBtn.disabled = false;
        }
      });
    }
    resultsGrid.appendChild(card);
  }
  updateSelectAllButtonState();
}

listBtn.addEventListener("click", async () => {
  resultsGrid.innerHTML = "";
  selectAllBtn.disabled = true;
  selectAllBtn.textContent = "Select all";
  listMeta.textContent = "";
  listError.textContent = "";
  try {
    ensureApiConfigured();
    const tag = tagInput.value.trim();
    const path = tag ? `/results?tag=${encodeURIComponent(tag)}` : "/results";
    const { data } = await getJson(path);

    const items = Array.isArray(data.items) ? data.items : [];
    if (items.length === 0) {
      if (pendingDocumentIds.size > 0) {
        listMeta.textContent = `No completed documents yet. ${pendingDocumentIds.size} recent upload(s) still processing...`;
      } else {
        listMeta.textContent = "No documents match this filter.";
      }
      selectAllBtn.disabled = true;
      selectAllBtn.textContent = "Select all";
      return;
    }

    const filterNote = data.tag ? ` tagged “${data.tag}”` : "";
    listMeta.textContent = `Showing ${items.length} document${items.length === 1 ? "" : "s"}${filterNote}.`;
    renderResultCards(items);
    if (pendingDocumentIds.size > 0) {
      listMeta.textContent += ` ${pendingDocumentIds.size} recent upload(s) still processing...`;
    }
  } catch (err) {
    listError.textContent = String(err.message || err);
  }
});

selectAllBtn.addEventListener("click", () => {
  selectAllVisibleCards();
});

deleteSelectedBtn.addEventListener("click", async () => {
  if (selectedDocumentIds.size === 0) return;
  const ids = Array.from(selectedDocumentIds);
  const confirmed = window.confirm(
    `Delete ${ids.length} selected document(s)?\nThis removes S3 objects and result metadata.`
  );
  if (!confirmed) return;
  deleteSelectedBtn.disabled = true;
  listError.textContent = "";
  let ok = 0;
  let failed = 0;
  for (const id of ids) {
    try {
      await deleteJson(`/results/${encodeURIComponent(id)}`);
      selectedDocumentIds.delete(id);
      ok += 1;
    } catch (_) {
      failed += 1;
    }
  }
  updateBatchDeleteButton();
  listMeta.textContent = `Batch delete finished. Deleted: ${ok}, Failed: ${failed}.`;
  listBtn.click();
});

function renderDetailView(data) {
  const summary = data.summary || "(No summary yet.)";
  const fileLabel = fileNameFromKey(data.key) || "(unknown file)";
  const tags = Array.isArray(data.tags) ? data.tags : [];

  const tagsHtml =
    tags.length > 0
      ? tags.map((t) => `<span class="tag-chip">${escapeHtml(t)}</span>`).join(" ")
      : "<span class=\"hint\">No tags</span>";

  detailPanel.innerHTML =
    `<p class="detail-filename">${escapeHtml(fileLabel)}</p>` +
    `<h3>Summary</h3>` +
    `<p class="summary-text">${escapeHtml(summary)}</p>` +
    `<h3>Tags</h3>` +
    `<div>${tagsHtml}</div>` +
    `<dl class="detail-meta">` +
    `<dt>Document ID</dt><dd>${escapeHtml(data.document_id)}</dd>` +
    `<dt>Status</dt><dd>${escapeHtml(data.status)}</dd>` +
    `<dt>Stored in S3</dt><dd>${escapeHtml(data.bucket || "")} / ${escapeHtml(data.key || "")}</dd>` +
    `</dl>`;

  detailPanel.hidden = false;
  detailRaw.textContent = pretty(data);
  detailRawWrap.hidden = false;
}

detailBtn.addEventListener("click", async () => {
  detailPanel.hidden = true;
  detailPanel.innerHTML = "";
  detailError.textContent = "";
  detailRawWrap.hidden = true;
  cacheIndicator.textContent = "";
  cacheIndicator.className = "cache";
  try {
    ensureApiConfigured();
    const docId = docIdInput.value.trim();
    if (!docId) {
      throw new Error("Enter a document ID.");
    }

    const { data, headers } = await getJson(`/results/${encodeURIComponent(docId)}`);
    const cache = headers.get("x-cache");
    if (cache) {
      cacheIndicator.textContent = `Cache: ${cache}`;
      cacheIndicator.classList.add(cache.toLowerCase() === "hit" ? "hit" : "miss");
    } else {
      cacheIndicator.textContent = "Cache: not visible in browser (CORS); use curl to verify HIT/MISS.";
    }
    renderDetailView(data);
  } catch (err) {
    detailError.textContent = String(err.message || err);
  }
});

saveApiBtn.addEventListener("click", () => {
  try {
    saveApiUrl();
  } catch (err) {
    apiOutput.textContent = String(err.message || err);
  }
});

(async function init() {
  const { url, source } = await resolveApiUrl();
  setApiUrl(url);
  apiUrlInput.value = apiBaseUrl;
  renderApiStatus(source);
  setSelectedFiles([]);
})();
