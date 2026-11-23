/* ==========================================================================
   VOID · local library dashboard
   Vanilla JS, no dependencies. All user-controlled strings are escaped before
   being placed into HTML; structured content is built with DOM nodes.
   ========================================================================== */

(() => {
  "use strict";

  const MAX_UPLOAD = 100 * 1024 * 1024;

  const PLACE_LABELS = {
    cloud: "VOID Cloud",
    local: "Local",
    gdrive: "Google Drive",
    github: "GitHub",
  };

  const STATE_LABELS = {
    in_sync: "In sync",
    pending: "Pending",
    conflict: "Conflict",
    missing: "Missing",
    error: "Error",
    detached: "Detached",
    unknown: "Unknown",
  };

  const ICON_FILE =
    '<svg class="icon" aria-hidden="true"><use href="#icon-file"></use></svg>';
  const ICON_DOWNLOAD =
    '<svg class="icon" aria-hidden="true"><use href="#icon-download"></use></svg>';
  const ICON_TRASH =
    '<svg class="icon" aria-hidden="true"><use href="#icon-trash"></use></svg>';

  const state = {
    documents: [],
    subjects: [],
    status: {},
    filter: { q: "", subject: "" },
    firstLoad: true,
    loadSeq: 0,
    syncing: false,
    uploading: false,
    emptyMode: "upload",
    lastFocused: null,
  };

  const $ = (selector, root = document) => root.querySelector(selector);

  const refs = {};

  /* ------------------------------------------------------------------------
     Small helpers
     ------------------------------------------------------------------------ */

  const ESCAPES = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ESCAPES[char]);
  }

  function slug(value, fallback = "unknown") {
    const cleaned = String(value ?? "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "");
    return cleaned || fallback;
  }

  function stateKey(value) {
    return String(value ?? "unknown")
      .trim()
      .toLowerCase()
      .replace(/[\s-]+/g, "_");
  }

  function stateClass(value) {
    return stateKey(value).replace(/_/g, "-");
  }

  function placeLabel(value) {
    const key = String(value ?? "").toLowerCase();
    if (Object.prototype.hasOwnProperty.call(PLACE_LABELS, key)) {
      return PLACE_LABELS[key];
    }
    return String(value || "Unknown");
  }

  function stateLabel(value) {
    const key = stateKey(value);
    if (Object.prototype.hasOwnProperty.call(STATE_LABELS, key)) {
      return STATE_LABELS[key];
    }
    return String(value || "Unknown");
  }

  function formatBytes(value) {
    const size = Number(value);
    if (!Number.isFinite(size) || size < 0) return "—";
    if (size === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let index = Math.floor(Math.log(size) / Math.log(1024));
    index = Math.min(Math.max(index, 0), units.length - 1);
    const number = size / Math.pow(1024, index);
    const rendered =
      index === 0 || number >= 10 ? Math.round(number) : number.toFixed(1);
    return `${rendered} ${units[index]}`;
  }

  function numberOrZero(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
  }

  function docId(document) {
    return String(document?.doc_id || document?.id || "");
  }

  function documentHasPending(document) {
    return (Array.isArray(document?.states) ? document.states : []).some(
      (value) => stateKey(value) === "pending"
    );
  }

  function setText(element, value) {
    if (element) element.textContent = String(value ?? "");
  }

  function setLibraryStatus(message) {
    setText(refs.libraryStatus, message);
  }

  /* ------------------------------------------------------------------------
     API
     ------------------------------------------------------------------------ */

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    headers.set("Accept", "application/json");

    const response = await fetch(path, {
      ...options,
      headers,
      cache: "no-store",
    });

    const contentType = response.headers.get("content-type") || "";
    let payload = null;
    if (contentType.includes("application/json")) {
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
    }

    if (!response.ok) {
      const message =
        payload && typeof payload.error === "string"
          ? payload.error
          : `Request failed (${response.status})`;
      throw new Error(message);
    }
    return payload;
  }

  /* ------------------------------------------------------------------------
     Toasts
     ------------------------------------------------------------------------ */

  const TOAST_GLYPHS = {
    success: "✓",
    error: "!",
    warn: "!",
    info: "i",
  };

  function showToast({
    title,
    message = "",
    tone = "info",
    timeout = 5200,
  }) {
    if (!refs.toasts) return;

    while (refs.toasts.children.length >= 4) {
      refs.toasts.firstElementChild?.remove();
    }

    const toast = document.createElement("div");
    toast.className = `toast toast-${tone}`;
    toast.setAttribute("role", tone === "error" ? "alert" : "status");

    const icon = document.createElement("span");
    icon.className = "toast-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = TOAST_GLYPHS[tone] || "i";

    const body = document.createElement("div");
    body.className = "toast-body";

    const heading = document.createElement("p");
    heading.className = "toast-title";
    heading.textContent = title || "Notice";
    body.appendChild(heading);

    if (message) {
      const copy = document.createElement("p");
      copy.className = "toast-message";
      copy.textContent = message;
      body.appendChild(copy);
    }

    const close = document.createElement("button");
    close.className = "toast-close";
    close.type = "button";
    close.setAttribute("aria-label", "Dismiss notification");
    close.innerHTML =
      '<svg class="icon" aria-hidden="true"><use href="#icon-close"></use></svg>';

    toast.append(icon, body, close);
    refs.toasts.appendChild(toast);

    let dismissed = false;
    let timer = null;

    const dismiss = () => {
      if (dismissed) return;
      dismissed = true;
      if (timer) clearTimeout(timer);
      toast.classList.add("is-leaving");
      window.setTimeout(() => toast.remove(), 260);
    };

    close.addEventListener("click", dismiss);
    timer = window.setTimeout(dismiss, timeout);
  }

  /* ------------------------------------------------------------------------
     Loading and rendering
     ------------------------------------------------------------------------ */

  function setRefreshing(busy) {
    if (!refs.refreshBtn) return;
    refs.refreshBtn.classList.toggle("is-busy", busy);
    refs.refreshBtn.disabled = busy;
    refs.refreshBtn.setAttribute("aria-busy", busy ? "true" : "false");
    refs.libraryPanel?.setAttribute("aria-busy", busy ? "true" : "false");
  }

  function setButtonBusy(button, busy, busyText) {
    if (!button) return;
    button.classList.toggle("is-busy", busy);
    button.disabled = busy;
    button.setAttribute("aria-busy", busy ? "true" : "false");

    const label = button.querySelector(".btn-text");
    if (!label) return;

    if (busy && busyText) {
      if (!label.dataset.idle) label.dataset.idle = label.textContent;
      label.textContent = busyText;
    } else if (!busy && label.dataset.idle) {
      label.textContent = label.dataset.idle;
    }
  }

  function animateNumber(element, target) {
    if (!element) return;
    const value = numberOrZero(target);
    const previous = numberOrZero(element.dataset.value);
    element.dataset.value = String(value);

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    if (reduceMotion || previous === value) {
      element.textContent = String(value);
      return;
    }

    const started = performance.now();
    const duration = 420;

    const frame = (now) => {
      const progress = Math.min(1, (now - started) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = Math.round(previous + (value - previous) * eased);
      element.textContent = String(current);
      if (progress < 1) requestAnimationFrame(frame);
    };

    requestAnimationFrame(frame);
  }

  function renderSkeleton() {
    if (!refs.documentsBody) return;
    const rows = Array.from({ length: 5 })
      .map(
        () => `
          <tr class="skeleton-row" aria-hidden="true">
            <td class="doc-cell-td">
              <div class="doc-cell">
                <span class="skeleton skeleton-icon"></span>
                <div class="doc-main">
                  <span class="skeleton skeleton-block"></span>
                  <span class="skeleton skeleton-block short"></span>
                </div>
              </div>
            </td>
            <td><span class="skeleton skeleton-block short"></span></td>
            <td><span class="skeleton skeleton-block"></span></td>
            <td><span class="skeleton skeleton-block short"></span></td>
            <td><span class="skeleton skeleton-block short"></span></td>
            <td></td>
          </tr>`
      )
      .join("");

    refs.documentsBody.innerHTML = rows;
    if (refs.tableWrap) refs.tableWrap.hidden = false;
    if (refs.emptyState) refs.emptyState.hidden = true;
    setText(refs.libraryCount, "Loading catalog…");
  }

  async function loadAll({ silent = false } = {}) {
    const token = ++state.loadSeq;
    if (!silent) setRefreshing(true);

    try {
      const [status, documentsPayload] = await Promise.all([
        api("/api/status"),
        api("/api/documents"),
      ]);

      if (token !== state.loadSeq) return;

      state.status = status && typeof status === "object" ? status : {};
      state.documents = Array.isArray(documentsPayload?.documents)
        ? documentsPayload.documents
        : [];
      state.subjects = Array.isArray(state.status.subjects)
        ? state.status.subjects
        : [];

      renderAll();
      state.firstLoad = false;
      setLibraryStatus(
        `Loaded ${state.documents.length} document${
          state.documents.length === 1 ? "" : "s"
        }.`
      );
    } catch (error) {
      if (token !== state.loadSeq) return;
      if (state.firstLoad || state.documents.length === 0) {
        renderLoadError(error);
      }
      showToast({
        tone: "error",
        title: "Could not load the library",
        message: error.message || "Unknown error",
      });
    } finally {
      if (token === state.loadSeq) {
        setRefreshing(false);
      }
    }
  }

  function renderAll() {
    renderIdentity();
    renderStats();
    renderPlaces();
    renderSubjectOptions();
    renderDocuments();
  }

  function renderIdentity() {
    const userId = String(state.status?.user_id || "local");
    setText(refs.userId, userId);
    setText(refs.nodeUser, userId);
    setText(refs.nodeHost, window.location.host || "127.0.0.1:8000");
    setText(refs.host, window.location.host || "127.0.0.1:8000");

    const pending = pendingCount();
    setText(refs.nodePending, pending === 0 ? "none" : `${pending} queued`);
  }

  function connectedPlaces() {
    const places = Array.isArray(state.status?.places)
      ? state.status.places
      : [];
    return places.filter((place) => place && place.connected === true);
  }

  function pendingCount() {
    if (state.status && state.status.pending !== undefined) {
      return numberOrZero(state.status.pending);
    }
    return state.documents.filter(documentHasPending).length;
  }

  function renderStats() {
    const documents = Number.isFinite(Number(state.status?.documents))
      ? numberOrZero(state.status.documents)
      : state.documents.length;
    const subjects = Array.isArray(state.status?.subjects)
      ? state.status.subjects.length
      : state.subjects.length;
    const places = connectedPlaces().length;
    const pending = pendingCount();

    animateNumber(refs.statDocuments, documents);
    animateNumber(refs.statSubjects, subjects);
    animateNumber(refs.statPlaces, places);
    animateNumber(refs.statPending, pending);

    refs.pendingCard?.classList.toggle("is-alert", pending > 0);
  }

  function renderPlaces() {
    if (!refs.placesList) return;
    refs.placesList.replaceChildren();

    const places = Array.isArray(state.status?.places)
      ? state.status.places
      : [];

    if (places.length === 0) {
      const empty = document.createElement("p");
      empty.className = "places-note";
      empty.textContent = "No storage places were reported by the library.";
      refs.placesList.appendChild(empty);
      return;
    }

    for (const place of places) {
      const name = String(place?.name || "Unknown place");
      const detail = String(place?.detail || "");
      const connected = place?.connected === true;

      const row = document.createElement("div");
      row.className = "place";
      row.setAttribute(
        "aria-label",
        `${name}: ${connected ? "connected" : "offline"}${
          detail ? `. ${detail}` : ""
        }`
      );

      const dot = document.createElement("span");
      dot.className = `place-dot${connected ? " online" : ""}`;
      dot.setAttribute("aria-hidden", "true");

      const body = document.createElement("div");
      body.className = "place-body";

      const heading = document.createElement("div");
      heading.className = "place-name";

      const label = document.createElement("span");
      label.textContent = name;

      const status = document.createElement("span");
      status.className = `place-status${connected ? "" : " offline"}`;
      status.textContent = connected ? "ONLINE" : "OFFLINE";

      heading.append(label, status);
      body.appendChild(heading);

      if (detail) {
        const description = document.createElement("p");
        description.className = "place-detail";
        description.textContent = detail;
        body.appendChild(description);
      }

      row.append(dot, body);
      refs.placesList.appendChild(row);
    }
  }

  function renderSubjectOptions() {
    if (!refs.subjectFilter) return;

    const selected = refs.subjectFilter.value || state.filter.subject;
    const fragment = document.createDocumentFragment();
    fragment.appendChild(new Option("All subjects", ""));

    for (const subject of state.subjects) {
      const text = String(subject ?? "").trim();
      if (!text) continue;
      fragment.appendChild(new Option(text, text));
    }

    refs.subjectFilter.replaceChildren(fragment);

    const stillExists = state.subjects.some(
      (subject) => String(subject) === selected
    );
    if (selected && stillExists) {
      refs.subjectFilter.value = selected;
      state.filter.subject = selected;
    } else {
      refs.subjectFilter.value = "";
      state.filter.subject = "";
    }

    if (refs.subjectOptions) {
      const options = document.createDocumentFragment();
      for (const subject of state.subjects) {
        const text = String(subject ?? "").trim();
        if (!text) continue;
        const option = document.createElement("option");
        option.value = text;
        options.appendChild(option);
      }
      refs.subjectOptions.replaceChildren(options);
    }
  }

  function filteredDocuments() {
    const query = state.filter.q.trim().toLowerCase();
    const subject = state.filter.subject.trim();

    return state.documents.filter((document) => {
      if (subject) {
        const documentSubject = String(document?.subject || "");
        if (documentSubject.toUpperCase() !== subject.toUpperCase()) {
          return false;
        }
      }
      if (!query) return true;
      const title = String(document?.title || "").toLowerCase();
      const summary = String(document?.summary || "").toLowerCase();
      return title.includes(query) || summary.includes(query);
    });
  }

  function renderDocuments() {
    if (!refs.documentsBody) return;

    const filtered = filteredDocuments();
    const total = state.documents.length;

    if (refs.libraryCount) {
      if (total === 0) {
        setText(refs.libraryCount, "0 documents indexed");
      } else if (filtered.length === total) {
        setText(
          refs.libraryCount,
          `${total} document${total === 1 ? "" : "s"} indexed`
        );
      } else {
        setText(
          refs.libraryCount,
          `${filtered.length} of ${total} document${
            total === 1 ? "" : "s"
          } shown`
        );
      }
    }

    if (total === 0) {
      refs.documentsBody.replaceChildren();
      showEmpty({
        title: "The void is empty",
        text: "Upload your first file and it will show up here, sorted and ready.",
        action: "Upload a file",
        mode: "upload",
      });
      return;
    }

    if (filtered.length === 0) {
      refs.documentsBody.replaceChildren();
      showEmpty({
        title: "Nothing matches",
        text: "No documents match this search and subject filter. Try clearing them.",
        action: "Clear filters",
        mode: "clear",
      });
      return;
    }

    if (refs.emptyState) refs.emptyState.hidden = true;
    if (refs.tableWrap) refs.tableWrap.hidden = false;

    refs.documentsBody.innerHTML = filtered.map(documentRow).join("");
    setLibraryStatus(
      `Showing ${filtered.length} of ${total} document${
        total === 1 ? "" : "s"
      }.`
    );
  }

  function showEmpty({ title, text, action, mode }) {
    if (refs.tableWrap) refs.tableWrap.hidden = true;
    if (!refs.emptyState) return;

    refs.emptyState.hidden = false;
    state.emptyMode = mode;
    setText(refs.emptyTitle, title);
    setText(refs.emptyText, text);
    setText(refs.emptyActionText, action);

    const use = refs.emptyAction?.querySelector("use");
    if (use) {
      const icon =
        mode === "clear"
          ? "#icon-close"
          : mode === "retry"
            ? "#icon-refresh"
            : "#icon-upload";
      use.setAttribute("href", icon);
    }
  }

  function documentRow(document) {
    const id = docId(document);
    const title = String(document?.title || "Untitled");
    const summary = String(document?.summary || "");
    const subject = String(document?.subject || "UNSORTED");
    const docType = String(document?.doc_type || "FILE");
    const mime = String(document?.mime || "unknown type");
    const shortMime = mime.length > 34 ? `${mime.slice(0, 31)}…` : mime;
    const labelTitle = title.replace(/\s+/g, " ").trim();

    const places = Array.isArray(document?.places) ? document.places : [];
    const states = Array.isArray(document?.states) ? document.states : [];

    const placesHtml = places.length
      ? places
          .map(
            (place) =>
              `<span class="pill place-${slug(place)}">${escapeHtml(
                placeLabel(place)
              )}</span>`
          )
          .join("")
      : '<span class="muted">No copies</span>';

    const statesHtml = (states.length ? states : ["unknown"])
      .map(
        (value) =>
          `<span class="badge state-${stateClass(
            value
          )}"><span class="badge-dot"></span>${escapeHtml(
            stateLabel(value)
          )}</span>`
      )
      .join("");

    const summaryHtml =
      summary && summary !== title
        ? `<p class="doc-summary" title="${escapeHtml(summary)}">${escapeHtml(
            summary
          )}</p>`
        : "";

    return `
      <tr>
        <td class="doc-cell-td" data-label="Document">
          <div class="doc-cell">
            <span class="doc-icon" aria-hidden="true">${ICON_FILE}</span>
            <div class="doc-main">
              <span class="doc-name" title="${escapeHtml(title)}">${escapeHtml(
                title
              )}</span>
              ${summaryHtml}
              <div class="doc-meta">
                <span>${escapeHtml(docType)}</span>
                <span class="sep">/</span>
                <span>${escapeHtml(shortMime)}</span>
              </div>
            </div>
          </div>
        </td>
        <td data-label="Subject">
          <span class="subject-pill" title="${escapeHtml(
            subject
          )}">${escapeHtml(subject)}</span>
        </td>
        <td data-label="Places">
          <div class="pill-row">${placesHtml}</div>
        </td>
        <td data-label="State">
          <div class="state-badge-stack">${statesHtml}</div>
        </td>
        <td class="size-cell" data-label="Size">${escapeHtml(
          formatBytes(document?.size)
        )}</td>
        <td data-label="Actions">
          <div class="row-actions">
            <button
              class="btn btn-icon"
              type="button"
              data-action="download"
              data-id="${escapeHtml(id)}"
              aria-label="Download ${escapeHtml(labelTitle)}"
              title="Download"
            >${ICON_DOWNLOAD}</button>
            <button
              class="btn btn-icon btn-delete"
              type="button"
              data-action="delete"
              data-id="${escapeHtml(id)}"
              aria-label="Delete ${escapeHtml(labelTitle)}"
              title="Delete"
            >${ICON_TRASH}</button>
          </div>
        </td>
      </tr>`;
  }

  function renderLoadError(error) {
    if (refs.tableWrap) refs.tableWrap.hidden = true;
    setText(refs.libraryCount, "Connection error");
    setText(refs.statDocuments, "—");
    setText(refs.statSubjects, "—");
    setText(refs.statPlaces, "—");
    setText(refs.statPending, "—");
    refs.pendingCard?.classList.remove("is-alert");
    showEmpty({
      title: "Library unavailable",
      text:
        error.message ||
        "The dashboard could not reach the library. Check the server and retry.",
      action: "Retry",
      mode: "retry",
    });
  }

  /* ------------------------------------------------------------------------
     Actions
     ------------------------------------------------------------------------ */

  async function handleSync() {
    if (state.syncing) return;
    state.syncing = true;
    setButtonBusy(refs.syncBtn, true, "Syncing…");

    try {
      const payload = await api("/api/sync", { method: "POST" });
      if (payload?.status && typeof payload.status === "object") {
        state.status = payload.status;
      }
      await loadAll({ silent: true });

      const report = payload?.report || {};
      const problems =
        numberOrZero(report.error) + numberOrZero(report.conflict);

      setText(
        refs.lastSync,
        new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        })
      );

      showToast({
        tone: problems > 0 ? "warn" : "success",
        title: problems > 0 ? "Sync finished with notes" : "Sync complete",
        message: formatReport(report),
        timeout: 7000,
      });
    } catch (error) {
      showToast({
        tone: "error",
        title: "Sync failed",
        message: error.message || "Unknown error",
      });
    } finally {
      state.syncing = false;
      setButtonBusy(refs.syncBtn, false);
    }
  }

  function formatReport(report) {
    const part = (key, symbol, label) =>
      `${symbol} ${numberOrZero(report?.[key])} ${label}`;
    const pieces = [
      part("upload", "↑", "uploaded"),
      part("download", "↓", "downloaded"),
      part("conflict", "⚠", "conflicts"),
      part("pending", "⏳", "pending"),
      part("missing", "✗", "missing"),
    ];
    if (numberOrZero(report?.error) > 0) {
      pieces.push(`! ${numberOrZero(report.error)} errors`);
    }
    return pieces.join(" · ");
  }

  async function handleRefresh() {
    await loadAll();
  }

  function handleDownload(id) {
    if (!id) return;
    const anchor = document.createElement("a");
    anchor.href = `/api/download/${encodeURIComponent(id)}`;
    anchor.download = "";
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();

    showToast({
      tone: "info",
      title: "Download started",
      message: "Your browser is fetching a readable copy from the library.",
    });
  }

  async function handleDelete(id) {
    if (!id) return;
    const document = state.documents.find((item) => docId(item) === id);
    const title = document?.title || "this file";

    if (
      !window.confirm(
        `Delete “${title}” from every connected place?\n\nThis cannot be undone.`
      )
    ) {
      return;
    }

    try {
      const payload = await api(`/api/delete/${encodeURIComponent(id)}`, {
        method: "POST",
        body: JSON.stringify({ confirm: true }),
      });
      const errors = Array.isArray(payload?.errors) ? payload.errors : [];

      if (errors.length) {
        showToast({
          tone: "warn",
          title: "Deleted with warnings",
          message: errors.join(" · "),
          timeout: 8000,
        });
      } else {
        showToast({
          tone: "success",
          title: "Document deleted",
          message: `${title} was removed from the catalog and its places.`,
        });
      }
      await loadAll({ silent: true });
    } catch (error) {
      showToast({
        tone: "error",
        title: "Delete failed",
        message: error.message || "Unknown error",
      });
    }
  }

  /* ------------------------------------------------------------------------
     Upload modal
     ------------------------------------------------------------------------ */

  function openUpload() {
    if (!refs.modal) return;
    state.lastFocused = document.activeElement;

    refs.uploadForm?.reset();
    setText(refs.fileName, "No file selected");
    refs.fileName?.classList.remove("has-file");
    hideModalError();
    hideUploadResults();
    if (refs.uploadSubmit) {
      refs.uploadSubmit.hidden = false;
      setButtonBusy(refs.uploadSubmit, false);
    }
    setText(refs.uploadCancel, "Cancel");

    if (refs.subjectInput) {
      refs.subjectInput.value = state.filter.subject || "";
    }

    refs.modal.hidden = false;
    document.body.classList.add("modal-open");
    window.setTimeout(() => refs.modalCard?.focus(), 40);
  }

  function closeUpload() {
    if (!refs.modal || refs.modal.hidden) return;
    refs.modal.hidden = true;
    document.body.classList.remove("modal-open");
    if (state.lastFocused instanceof HTMLElement) {
      state.lastFocused.focus();
    }
  }

  function showModalError(message) {
    if (!refs.modalError) return;
    refs.modalError.textContent = String(message || "Something went wrong.");
    refs.modalError.hidden = false;
  }

  function hideModalError() {
    if (!refs.modalError) return;
    refs.modalError.hidden = true;
    refs.modalError.textContent = "";
  }

  function hideUploadResults() {
    if (refs.uploadResults) refs.uploadResults.hidden = true;
    refs.uploadResultsList?.replaceChildren();
    refs.uploadErrors?.replaceChildren();
  }

  function renderUploadResults(result) {
    if (!refs.uploadResults) return;
    refs.uploadResults.hidden = false;
    refs.uploadResultsList?.replaceChildren();
    refs.uploadErrors?.replaceChildren();

    const results = Array.isArray(result?.results) ? result.results : [];
    if (results.length === 0) {
      const row = document.createElement("div");
      row.className = "result-row";
      const path = document.createElement("span");
      path.className = "result-path";
      path.textContent = "No places reported.";
      row.appendChild(path);
      refs.uploadResultsList?.appendChild(row);
    }

    for (const item of results) {
      const row = document.createElement("div");
      row.className = "result-row";

      const place = document.createElement("span");
      place.className = `pill place-${slug(item?.place)}`;
      place.textContent = placeLabel(item?.place);

      const path = document.createElement("span");
      path.className = "result-path";
      path.title = String(item?.path || "");
      path.textContent = String(item?.path || "");

      const status = document.createElement("span");
      const statusValue = String(item?.status || "unknown").toLowerCase();
      const statusClass =
        statusValue === "ok" ? "ok" : statusValue === "pending" ? "pending" : "error";
      status.className = `result-status ${statusClass}`;
      status.textContent = statusValue.toUpperCase();

      row.append(place, path, status);
      refs.uploadResultsList?.appendChild(row);
    }

    const errors = Array.isArray(result?.errors) ? result.errors : [];
    for (const error of errors) {
      const line = document.createElement("div");
      line.className = "result-error";
      line.textContent = String(error);
      refs.uploadErrors?.appendChild(line);
    }
  }

  async function handleUpload(event) {
    event.preventDefault();
    if (state.uploading || refs.uploadSubmit?.hidden) return;
    hideModalError();

    const file = refs.fileInput?.files?.[0];
    if (!file) {
      showModalError("Choose a file to upload first.");
      refs.fileInput?.focus();
      return;
    }
    if (file.size > MAX_UPLOAD) {
      showModalError("That file is larger than the 100 MB limit.");
      return;
    }

    const subject = (refs.subjectInput?.value || "").trim() || "UNSORTED";
    const docType = (refs.docType?.value || "").trim();
    const summary = (refs.summary?.value || "").trim();

    const formData = new FormData();
    formData.append("file", file, file.name);
    formData.append("subject", subject);
    if (docType) formData.append("doc_type", docType);
    if (summary) formData.append("summary", summary);

    state.uploading = true;
    hideUploadResults();
    setButtonBusy(refs.uploadSubmit, true, "Uploading…");

    try {
      const result = await api("/api/upload", {
        method: "POST",
        body: formData,
      });

      renderUploadResults(result);
      await loadAll({ silent: true });

      const errors = Array.isArray(result?.errors) ? result.errors : [];
      const places = Array.isArray(result?.results) ? result.results : [];
      const okCount = places.filter(
        (item) => String(item?.status || "").toLowerCase() === "ok"
      ).length;
      const pendingCount = places.length - okCount;

      showToast({
        tone: errors.length ? "warn" : "success",
        title: errors.length ? "Uploaded with warnings" : "File added to the library",
        message: [
          `${subject} · ${file.name}`,
          places.length
            ? `${okCount} place${okCount === 1 ? "" : "s"} synced${
                pendingCount ? `, ${pendingCount} pending` : ""
              }`
            : "",
        ]
          .filter(Boolean)
          .join(" · "),
        timeout: errors.length ? 8000 : 5000,
      });

      if (refs.uploadSubmit) refs.uploadSubmit.hidden = true;
      setText(refs.uploadCancel, "Close");
    } catch (error) {
      showModalError(error.message || "Upload failed.");
      showToast({
        tone: "error",
        title: "Upload failed",
        message: error.message || "Unknown error",
      });
    } finally {
      state.uploading = false;
      setButtonBusy(refs.uploadSubmit, false);
    }
  }

  function handleFilePicked() {
    const file = refs.fileInput?.files?.[0];
    if (!file) {
      setText(refs.fileName, "No file selected");
      refs.fileName?.classList.remove("has-file");
      return;
    }
    setText(refs.fileName, `${file.name} · ${formatBytes(file.size)}`);
    refs.fileName?.classList.add("has-file");
  }

  function wireDropZone() {
    if (!refs.dropZone || !refs.fileInput) return;

    const highlight = (active) => {
      refs.dropZone.classList.toggle("is-dragover", active);
    };

    for (const eventName of ["dragenter", "dragover"]) {
      refs.dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        highlight(true);
      });
    }

    for (const eventName of ["dragleave", "drop"]) {
      refs.dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        highlight(false);
      });
    }

    refs.dropZone.addEventListener("drop", (event) => {
      const files = event.dataTransfer?.files;
      if (!files || files.length === 0) return;
      try {
        refs.fileInput.files = files;
      } catch {
        return;
      }
      handleFilePicked();
    });
  }

  /* ------------------------------------------------------------------------
     Search / filters
     ------------------------------------------------------------------------ */

  let searchTimer = null;

  function handleSearchInput() {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.filter.q = refs.search?.value || "";
      renderDocuments();
    }, 120);
  }

  function handleSubjectChange() {
    state.filter.subject = refs.subjectFilter?.value || "";
    renderDocuments();
  }

  function clearFilters() {
    if (refs.search) refs.search.value = "";
    if (refs.subjectFilter) refs.subjectFilter.value = "";
    state.filter.q = "";
    state.filter.subject = "";
    renderDocuments();
    refs.search?.focus();
  }

  function handleEmptyAction() {
    if (state.emptyMode === "clear") {
      clearFilters();
    } else if (state.emptyMode === "retry") {
      loadAll();
    } else {
      openUpload();
    }
  }

  /* ------------------------------------------------------------------------
     Wiring
     ------------------------------------------------------------------------ */

  function cacheRefs() {
    refs.host = $("#host");
    refs.userId = $("#user-id");
    refs.refreshBtn = $("#refresh-btn");
    refs.libraryPanel = $(".library-panel");
    refs.libraryStatus = $("#library-status");
    refs.libraryCount = $("#library-count");
    refs.statDocuments = $("#stat-documents");
    refs.statSubjects = $("#stat-subjects");
    refs.statPlaces = $("#stat-places");
    refs.statPending = $("#stat-pending");
    refs.pendingCard = $("#pending-card");
    refs.placesList = $("#places-list");
    refs.nodeUser = $("#node-user");
    refs.nodeHost = $("#node-host");
    refs.nodePending = $("#node-pending");
    refs.lastSync = $("#last-sync");
    refs.search = $("#search");
    refs.subjectFilter = $("#subject-filter");
    refs.syncBtn = $("#sync-btn");
    refs.uploadBtn = $("#upload-btn");
    refs.tableWrap = $("#table-wrap");
    refs.documentsTable = $("#documents-table");
    refs.documentsBody = $("#documents-body");
    refs.emptyState = $("#empty-state");
    refs.emptyTitle = $("#empty-title");
    refs.emptyText = $("#empty-text");
    refs.emptyAction = $("#empty-action");
    refs.emptyActionText = $("#empty-action-text");
    refs.modal = $("#upload-modal");
    refs.modalCard = $(".modal-card");
    refs.uploadForm = $("#upload-form");
    refs.dropZone = $("#drop-zone");
    refs.fileInput = $("#file-input");
    refs.fileName = $("#file-name");
    refs.subjectInput = $("#subject-input");
    refs.subjectOptions = $("#subject-options");
    refs.docType = $("#doc-type");
    refs.summary = $("#summary");
    refs.modalError = $("#modal-error");
    refs.uploadResults = $("#upload-results");
    refs.uploadResultsList = $("#upload-results-list");
    refs.uploadErrors = $("#upload-errors");
    refs.uploadSubmit = $("#upload-submit");
    refs.uploadCancel = $("#upload-cancel");
    refs.toasts = $("#toasts");
  }

  function wireEvents() {
    refs.refreshBtn?.addEventListener("click", handleRefresh);
    refs.syncBtn?.addEventListener("click", handleSync);
    refs.uploadBtn?.addEventListener("click", openUpload);
    refs.emptyAction?.addEventListener("click", handleEmptyAction);

    refs.search?.addEventListener("input", handleSearchInput);
    refs.subjectFilter?.addEventListener("change", handleSubjectChange);

    refs.fileInput?.addEventListener("change", handleFilePicked);
    refs.uploadForm?.addEventListener("submit", handleUpload);
    wireDropZone();

    for (const closer of document.querySelectorAll("[data-close-modal]")) {
      closer.addEventListener("click", closeUpload);
    }

    refs.documentsBody?.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      const id = button.getAttribute("data-id") || "";
      const action = button.getAttribute("data-action");
      if (action === "download") handleDownload(id);
      if (action === "delete") handleDelete(id);
    });

    document.addEventListener("keydown", (event) => {
      const target = event.target;
      const typing =
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable);

      if (event.key === "Escape") {
        if (refs.modal && !refs.modal.hidden) {
          closeUpload();
          return;
        }
        if (document.activeElement === refs.search && refs.search?.value) {
          clearFilters();
        }
        return;
      }

      if (
        event.key === "/" &&
        !typing &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey &&
        (!refs.modal || refs.modal.hidden)
      ) {
        event.preventDefault();
        refs.search?.focus();
      }
    });
  }

  function init() {
    cacheRefs();
    wireEvents();
    initTabs();
    wireSettings();

    const host = window.location.host || "127.0.0.1:8000";
    setText(refs.host, host);
    setText(refs.nodeHost, host);
    setText(refs.lastSync, "not this session");

    renderSkeleton();
    loadAll();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }

  /* ------------------------------------------------------------------------
     Tab switching
     ------------------------------------------------------------------------ */

  function initTabs() {
    const tabs = document.querySelectorAll('.tab-btn');
    const panels = document.querySelectorAll('.tab-panel');
    tabs.forEach(btn => {
      btn.addEventListener('click', () => {
        tabs.forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected', 'false'); });
        panels.forEach(p => p.hidden = true);
        btn.classList.add('active');
        btn.setAttribute('aria-selected', 'true');
        const target = document.getElementById('tab-' + btn.dataset.tab);
        if (target) target.hidden = false;
        if (btn.dataset.tab === 'settings') loadConfig();
      });
    });
  }

  /* ------------------------------------------------------------------------
     Settings
     ------------------------------------------------------------------------ */

  async function loadConfig() {
    try {
      const cfg = await api('/api/config');
      renderConfig(cfg);
    } catch(e) {
      showToast({ tone: 'error', title: 'Could not load config', message: e.message });
    }
  }

  function renderConfig(cfg) {
    // Local folder
    const localDot = document.getElementById('local-dot');
    const localBadge = document.getElementById('local-badge');
    const localRoot = document.getElementById('local-root');
    if (cfg.local?.enabled && cfg.local?.root) {
      localDot?.classList.add('online');
      if (localBadge) localBadge.textContent = 'Connected';
      if (localBadge) localBadge.className = 'settings-badge connected';
      if (localRoot) localRoot.value = cfg.local.root;
    } else {
      localDot?.classList.remove('online');
      if (localBadge) localBadge.textContent = 'Not connected';
      if (localBadge) localBadge.className = 'settings-badge';
      if (localRoot) localRoot.value = '';
    }

    // GitHub
    const githubDot = document.getElementById('github-dot');
    const githubBadge = document.getElementById('github-badge');
    if (cfg.github?.enabled && cfg.github?.token_set) {
      githubDot?.classList.add('online');
      if (githubBadge) githubBadge.textContent = 'Connected';
      if (githubBadge) githubBadge.className = 'settings-badge connected';
    } else {
      githubDot?.classList.remove('online');
      if (githubBadge) githubBadge.textContent = 'Not connected';
      if (githubBadge) githubBadge.className = 'settings-badge';
    }
    const githubRepo = document.getElementById('github-repo');
    const githubBranch = document.getElementById('github-branch');
    const githubRoot = document.getElementById('github-root');
    if (githubRepo) githubRepo.value = cfg.github?.repo || '';
    if (githubBranch) githubBranch.value = cfg.github?.branch || 'main';
    if (githubRoot) githubRoot.value = cfg.github?.root || 'VOID';

    // Google Drive
    const gdriveDot = document.getElementById('gdrive-dot');
    const gdriveBadge = document.getElementById('gdrive-badge');
    const gdriveOAuthNote = document.getElementById('gdrive-oauth-note');
    const gdriveClientId = document.getElementById('gdrive-client-id');
    if (cfg.gdrive?.enabled && cfg.gdrive?.refresh_token_set) {
      gdriveDot?.classList.add('online');
      if (gdriveBadge) gdriveBadge.textContent = 'Connected';
      if (gdriveBadge) gdriveBadge.className = 'settings-badge connected';
      if (gdriveOAuthNote) gdriveOAuthNote.hidden = false;
    } else {
      gdriveDot?.classList.remove('online');
      if (gdriveBadge) gdriveBadge.textContent = cfg.gdrive?.client_id ? 'Credentials saved' : 'Not connected';
      if (gdriveBadge) gdriveBadge.className = cfg.gdrive?.client_id ? 'settings-badge pending' : 'settings-badge';
      if (gdriveOAuthNote) gdriveOAuthNote.hidden = true;
    }
    if (gdriveClientId) gdriveClientId.value = cfg.gdrive?.client_id || '';
  }

  function wireSettings() {
    // Local folder save
    document.getElementById('local-form')?.addEventListener('submit', async e => {
      e.preventDefault();
      const root = document.getElementById('local-root')?.value.trim() || '';
      const hint = document.getElementById('local-hint');
      try {
        await api('/api/config/local', { method: 'POST', body: JSON.stringify({ root }) });
        if (hint) hint.textContent = root ? 'Local folder saved.' : 'Local folder removed.';
        showToast({ tone: 'success', title: root ? 'Local folder saved' : 'Local folder removed', message: root || '' });
        await loadConfig();
      } catch(e) { if (hint) hint.textContent = e.message; showToast({ tone: 'error', title: 'Error', message: e.message }); }
    });

    // Local folder remove
    document.getElementById('local-remove')?.addEventListener('click', async () => {
      const hint = document.getElementById('local-hint');
      try {
        await api('/api/config/local', { method: 'POST', body: JSON.stringify({ root: '' }) });
        if (hint) hint.textContent = 'Local folder removed.';
        showToast({ tone: 'success', title: 'Local folder removed' });
        await loadConfig();
      } catch(e) { if (hint) hint.textContent = e.message; }
    });

    // GitHub save
    document.getElementById('github-form')?.addEventListener('submit', async e => {
      e.preventDefault();
      const token = document.getElementById('github-token')?.value.trim() || '';
      const repo = document.getElementById('github-repo')?.value.trim() || '';
      const branch = document.getElementById('github-branch')?.value.trim() || 'main';
      const root = document.getElementById('github-root')?.value.trim() || 'VOID';
      const hint = document.getElementById('github-hint');
      try {
        await api('/api/config/github', { method: 'POST', body: JSON.stringify({ token, repo, branch, root }) });
        if (hint) hint.textContent = token ? 'GitHub connected.' : 'GitHub disconnected.';
        showToast({ tone: 'success', title: token ? 'GitHub saved' : 'GitHub disconnected' });
        await loadConfig();
      } catch(e) { if (hint) hint.textContent = e.message; showToast({ tone: 'error', title: 'Error', message: e.message }); }
    });

    // GitHub disconnect
    document.getElementById('github-disconnect')?.addEventListener('click', async () => {
      const hint = document.getElementById('github-hint');
      try {
        await api('/api/config/github', { method: 'POST', body: JSON.stringify({ token: '', repo: '', branch: 'main', root: 'VOID' }) });
        if (hint) hint.textContent = 'GitHub disconnected.';
        showToast({ tone: 'success', title: 'GitHub disconnected' });
        await loadConfig();
      } catch(e) { if (hint) hint.textContent = e.message; }
    });

    // GDrive save
    document.getElementById('gdrive-form')?.addEventListener('submit', async e => {
      e.preventDefault();
      const client_id = document.getElementById('gdrive-client-id')?.value.trim() || '';
      const client_secret = document.getElementById('gdrive-client-secret')?.value.trim() || '';
      const hint = document.getElementById('gdrive-hint');
      try {
        await api('/api/config/gdrive', { method: 'POST', body: JSON.stringify({ client_id, client_secret }) });
        if (hint) hint.textContent = client_id ? 'Credentials saved. Complete OAuth in the terminal.' : 'Google Drive disconnected.';
        showToast({ tone: 'success', title: client_id ? 'Drive credentials saved' : 'Google Drive disconnected' });
        await loadConfig();
      } catch(e) { if (hint) hint.textContent = e.message; showToast({ tone: 'error', title: 'Error', message: e.message }); }
    });

    // GDrive disconnect
    document.getElementById('gdrive-disconnect')?.addEventListener('click', async () => {
      const hint = document.getElementById('gdrive-hint');
      try {
        await api('/api/config/gdrive', { method: 'POST', body: JSON.stringify({ client_id: '', client_secret: '' }) });
        if (hint) hint.textContent = 'Google Drive disconnected.';
        showToast({ tone: 'success', title: 'Google Drive disconnected' });
        await loadConfig();
      } catch(e) { if (hint) hint.textContent = e.message; }
    });
  }

})();
