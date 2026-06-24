"use strict";

// ---- State ----
let savedRefs = new Set();        // source_refs already in the local library
let collectionsCache = [];        // [{id, name, count}]
let currentSaveItem = null;       // item shown in the save modal
let currentSaveBtn = null;        // its card button (to update after saving)

// ---- Source checkboxes ----
async function initSources() {
  const list = document.getElementById("sourceList");
  try {
    const res = await fetch("/api/sources");
    const data = await res.json();
    for (const s of data.sources) {
      const label = document.createElement("label");
      if (!s.ready) label.classList.add("disabled");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = s.key;
      cb.checked = s.ready;
      cb.disabled = !s.ready;
      label.appendChild(cb);
      label.appendChild(
        document.createTextNode(" " + s.label + (s.ready ? "" : " (precisa de chave)"))
      );
      list.appendChild(label);
    }
  } catch {
    list.innerHTML = "<legend>Fontes</legend><span>Não foi possível carregar as fontes.</span>";
  }
}

function selectedSources() {
  return [...document.querySelectorAll("#sourceList input:checked")]
    .map((cb) => cb.value)
    .join(",");
}

// ---- Library state sync ----
async function refreshSavedRefs() {
  try {
    const res = await fetch("/api/library/refs");
    const data = await res.json();
    savedRefs = new Set(data.refs);
    document.getElementById("libCount").textContent = savedRefs.size;
  } catch {
    /* ignore */
  }
}

async function loadCollections() {
  try {
    const res = await fetch("/api/collections");
    collectionsCache = (await res.json()).collections || [];
  } catch {
    collectionsCache = [];
  }
}

// ---- Search ----
const form = document.getElementById("searchForm");
const resultsEl = document.getElementById("results");
const statusEl = document.getElementById("status");
const notesEl = document.getElementById("notes");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = document.getElementById("query").value.trim();
  if (!q) return;
  const sources = selectedSources();
  if (!sources) {
    showStatus("Selecione pelo menos uma fonte.");
    return;
  }
  const minRes = document.getElementById("minRes").value;

  const btn = document.getElementById("searchBtn");
  btn.disabled = true;
  btn.textContent = "Buscando…";
  showStatus(`Buscando por “${q}”…`);
  resultsEl.innerHTML = "";
  notesEl.hidden = true;

  try {
    const url = `/api/search?q=${encodeURIComponent(q)}&sources=${sources}&min_res=${minRes}`;
    const res = await fetch(url);
    const data = await res.json();
    renderResults(data);
  } catch {
    showStatus("Algo deu errado. Tente novamente.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Buscar";
  }
});

function showStatus(text) {
  statusEl.textContent = text;
  statusEl.hidden = false;
}

function renderResults(data) {
  if (data.notes && data.notes.length) {
    notesEl.innerHTML =
      "<strong>Atenção:</strong><ul>" +
      data.notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("") +
      "</ul>";
    notesEl.hidden = false;
  }

  if (!data.results.length) {
    showStatus(`Nenhuma imagem para “${data.query}”. Tente termos mais amplos ou resolução menor.`);
    return;
  }

  const breakdown = Object.entries(data.per_source)
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${n} de ${k}`)
    .join(", ");
  showStatus(`${data.count} imagem(ns) encontrada(s) (${breakdown}).`);

  const tpl = document.getElementById("cardTemplate");
  const frag = document.createDocumentFragment();
  for (const item of data.results) frag.appendChild(buildCard(tpl, item));
  resultsEl.appendChild(frag);
}

function buildCard(tpl, item) {
  const node = tpl.content.cloneNode(true);
  const img = node.querySelector(".thumb");
  img.src = item.thumbnail;
  img.alt = item.title;
  img.addEventListener("error", () => {
    img.parentElement.classList.add("broken");
    img.style.display = "none";
  });

  node.querySelector(".source-badge").textContent = item.source;
  node.querySelector(".card-title").textContent = item.title;

  const creator = node.querySelector(".card-creator");
  if (item.creator) creator.textContent = item.creator;
  else creator.remove();

  node.querySelector(".card-license").textContent = item.license || "";

  const dims = node.querySelector(".card-dims");
  dims.textContent = item.width && item.height ? `${item.width} × ${item.height} px` : "Alta resolução";

  node.querySelector(".download").href =
    `/api/download?url=${encodeURIComponent(item.full_image)}&filename=${encodeURIComponent(item.title)}`;
  node.querySelector(".view").href = item.source_url || item.full_image;

  const saveBtn = node.querySelector(".save");
  syncSaveBtn(saveBtn, item.id);
  saveBtn.addEventListener("click", () => openSaveModal(item, saveBtn));

  return node;
}

// Lucide "star" icon (line, currentColor) used on the Save button.
const STAR_ICON =
  '<svg class="icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z" /></svg>';

function syncSaveBtn(btn, ref) {
  if (savedRefs.has(ref)) {
    btn.classList.add("saved");
    btn.innerHTML = STAR_ICON + " Salvo";
  } else {
    btn.classList.remove("saved");
    btn.innerHTML = STAR_ICON + " Salvar";
  }
}

// ---- Save modal ----
const modal = document.getElementById("saveModal");

async function openSaveModal(item, btn) {
  currentSaveItem = item;
  currentSaveBtn = btn;
  document.getElementById("saveModalSub").textContent = item.title;
  document.getElementById("saveTags").value = "";
  document.getElementById("newCollectionName").value = "";
  await loadCollections();
  renderCollectionChecklist([]);
  modal.hidden = false;
  document.getElementById("saveTags").focus();
}

function closeSaveModal() {
  modal.hidden = true;
  currentSaveItem = null;
  currentSaveBtn = null;
}

function renderCollectionChecklist(checkedIds) {
  const wrap = document.getElementById("saveCollections");
  if (!collectionsCache.length) {
    wrap.innerHTML = '<p class="muted-note">Nenhuma coleção ainda — crie uma abaixo.</p>';
    return;
  }
  wrap.innerHTML = "";
  for (const c of collectionsCache) {
    const label = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = c.id;
    cb.checked = checkedIds.includes(c.id);
    label.appendChild(cb);
    label.appendChild(document.createTextNode(` ${c.name} (${c.count})`));
    wrap.appendChild(label);
  }
}

document.getElementById("createCollectionBtn").addEventListener("click", async () => {
  const input = document.getElementById("newCollectionName");
  const name = input.value.trim();
  if (!name) return;
  try {
    const res = await fetch("/api/collections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    input.value = "";
    const checked = [...document.querySelectorAll("#saveCollections input:checked")].map((c) =>
      Number(c.value)
    );
    await loadCollections();
    renderCollectionChecklist([...checked, data.collection.id]);
  } catch {
    alert("Não foi possível criar a coleção.");
  }
});

document.getElementById("saveCancel").addEventListener("click", closeSaveModal);
modal.addEventListener("click", (e) => {
  if (e.target === modal) closeSaveModal();
});

document.getElementById("saveConfirm").addEventListener("click", async () => {
  if (!currentSaveItem) return;
  const confirmBtn = document.getElementById("saveConfirm");
  confirmBtn.disabled = true;
  confirmBtn.textContent = "Salvando…";

  const tags = document
    .getElementById("saveTags")
    .value.split(",")
    .map((t) => t.trim())
    .filter(Boolean);
  const collection_ids = [...document.querySelectorAll("#saveCollections input:checked")].map((c) =>
    Number(c.value)
  );

  try {
    const res = await fetch("/api/library/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...currentSaveItem, tags, collection_ids }),
    });
    if (!res.ok) {
      let msg = "Erro ao salvar.";
      try {
        msg = (await res.json()).detail || msg;
      } catch {
        /* keep default */
      }
      throw new Error(msg);
    }
    savedRefs.add(currentSaveItem.id);
    document.getElementById("libCount").textContent = savedRefs.size;
    if (currentSaveBtn) syncSaveBtn(currentSaveBtn, currentSaveItem.id);
    closeSaveModal();
  } catch (err) {
    alert(err.message);
  } finally {
    confirmBtn.disabled = false;
    confirmBtn.innerHTML =
      '<svg class="icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15V3" /><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="m7 10 5 5 5-5" /></svg> Salvar no HD';
  }
});

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---- Init ----
initSources();
refreshSavedRefs();
