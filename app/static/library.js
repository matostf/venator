"use strict";

// ---- State ----
let activeTag = null;
let activeCollection = "";
let searchText = "";
let allTags = [];
let allCollections = [];
let currentItem = null; // item open in the lightbox

const gridEl = document.getElementById("grid");
const statusEl = document.getElementById("status");

// ---- Load + render ----
async function loadAll() {
  await Promise.all([loadTags(), loadCollections()]);
  await loadImages();
  updateLibCount();
}

async function loadTags() {
  try {
    allTags = (await (await fetch("/api/tags")).json()).tags || [];
  } catch {
    allTags = [];
  }
  renderTagChips();
}

function renderTagChips() {
  const wrap = document.getElementById("tagChips");
  wrap.innerHTML = "";
  if (!allTags.length) return;

  const allChip = chip("Todas as tags", activeTag === null);
  allChip.addEventListener("click", () => {
    activeTag = null;
    renderTagChips();
    loadImages();
  });
  wrap.appendChild(allChip);

  for (const t of allTags) {
    const c = chip(`${t.name} (${t.count})`, activeTag === t.name);
    c.addEventListener("click", () => {
      activeTag = activeTag === t.name ? null : t.name;
      renderTagChips();
      loadImages();
    });
    wrap.appendChild(c);
  }
}

function chip(text, active) {
  const el = document.createElement("button");
  el.className = "chip" + (active ? " active" : "");
  el.textContent = text;
  return el;
}

async function loadCollections() {
  try {
    allCollections = (await (await fetch("/api/collections")).json()).collections || [];
  } catch {
    allCollections = [];
  }
  const sel = document.getElementById("collectionFilter");
  const current = sel.value;
  sel.innerHTML = '<option value="">Todas as coleções</option>';
  for (const c of allCollections) {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = `${c.name} (${c.count})`;
    sel.appendChild(opt);
  }
  sel.value = current;
}

async function loadImages() {
  const params = new URLSearchParams();
  if (activeTag) params.set("tag", activeTag);
  if (activeCollection) params.set("collection_id", activeCollection);
  if (searchText) params.set("q", searchText);

  statusEl.hidden = true;
  try {
    const data = await (await fetch("/api/library?" + params.toString())).json();
    renderImages(data.results);
  } catch {
    showStatus("Não foi possível carregar a biblioteca.");
  }
}

function showStatus(t) {
  statusEl.textContent = t;
  statusEl.hidden = false;
}

function renderImages(items) {
  gridEl.innerHTML = "";
  if (!items.length) {
    gridEl.innerHTML =
      '<p class="empty">Nenhuma imagem aqui ainda. Vá em <a href="/">🔎 Buscar</a> e clique em ★ Salvar.</p>';
    return;
  }
  const tpl = document.getElementById("libCardTemplate");
  const frag = document.createDocumentFragment();
  for (const item of items) frag.appendChild(buildCard(tpl, item));
  gridEl.appendChild(frag);
}

function buildCard(tpl, item) {
  const node = tpl.content.cloneNode(true);
  const img = node.querySelector(".thumb");
  img.src = `/api/library/${item.id}/thumb`;
  img.alt = item.title;

  node.querySelector(".source-badge").textContent = item.source || "";
  if (!item.notes) node.querySelector(".note-flag").remove();

  node.querySelector(".card-title").textContent = item.title;

  const creator = node.querySelector(".card-creator");
  if (item.creator) creator.textContent = item.creator;
  else creator.remove();

  node.querySelector(".card-license").textContent = item.license || "";

  const tagsWrap = node.querySelector(".card-tags");
  for (const t of item.tags || []) {
    const pill = document.createElement("span");
    pill.className = "tag-pill";
    pill.textContent = t;
    tagsWrap.appendChild(pill);
  }

  node.querySelector(".download").href = `/api/library/${item.id}/file`;
  node.querySelector(".details").addEventListener("click", () => openLightbox(item));
  node.querySelector(".remove").addEventListener("click", () => removeImage(item));
  // Clicking the image or body also opens the detail view.
  node.querySelectorAll(".clickable").forEach((el) =>
    el.addEventListener("click", () => openLightbox(item))
  );

  return node;
}

async function removeImage(item) {
  if (!confirm(`Remover “${item.title}” da biblioteca? O arquivo será apagado do HD.`)) return;
  try {
    await fetch(`/api/library/${item.id}`, { method: "DELETE" });
    await refreshAfterChange();
  } catch {
    alert("Não foi possível remover.");
  }
}

// ---- Lightbox ----
const lightbox = document.getElementById("lightbox");

async function openLightbox(item) {
  // Always fetch the freshest copy (notes/tags/collections may have changed).
  try {
    const fresh = (await (await fetch(`/api/library/${item.id}`)).json()).image;
    currentItem = fresh || item;
  } catch {
    currentItem = item;
  }
  const it = currentItem;

  document.getElementById("lbImg").src = `/api/library/${it.id}/view`;
  document.getElementById("lbImg").alt = it.title;
  document.getElementById("lbTitle").textContent = it.title;

  const creatorEl = document.getElementById("lbCreator");
  creatorEl.textContent = it.creator || "";
  creatorEl.style.display = it.creator ? "" : "none";

  const dims = it.width && it.height ? ` · ${it.width} × ${it.height} px` : "";
  document.getElementById("lbMeta").textContent =
    `${it.source || ""} · ${it.license || ""}${dims}`;

  document.getElementById("lbAttrib").textContent = it.attribution || "";
  document.getElementById("lbTags").value = (it.tags || []).join(", ");
  document.getElementById("lbNotes").value = it.notes || "";

  document.getElementById("lbDownload").href = `/api/library/${it.id}/file`;
  const src = document.getElementById("lbSource");
  if (it.source_url) {
    src.href = it.source_url;
    src.style.display = "";
  } else {
    src.style.display = "none";
  }

  renderLbCollections(it);
  lightbox.hidden = false;
}

function closeLightbox() {
  lightbox.hidden = true;
  currentItem = null;
}

function renderLbCollections(item) {
  const wrap = document.getElementById("lbCollections");
  wrap.innerHTML = "";
  if (!allCollections.length) {
    wrap.innerHTML = '<p class="muted-note">Nenhuma coleção. Crie uma na barra acima.</p>';
    return;
  }
  const memberIds = new Set((item.collections || []).map((c) => c.id));
  for (const c of allCollections) {
    const label = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = memberIds.has(c.id);
    cb.addEventListener("change", () => toggleCollection(c.id, cb.checked));
    label.appendChild(cb);
    label.appendChild(document.createTextNode(` ${c.name}`));
    wrap.appendChild(label);
  }
}

async function toggleCollection(collectionId, add) {
  if (!currentItem) return;
  const url = `/api/collections/${collectionId}/images/${currentItem.id}`;
  try {
    await fetch(url, { method: add ? "POST" : "DELETE" });
    await loadCollections(); // refresh counts
  } catch {
    alert("Não foi possível atualizar a coleção.");
  }
}

document.getElementById("lbClose").addEventListener("click", closeLightbox);
lightbox.addEventListener("click", (e) => {
  if (e.target === lightbox) closeLightbox();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !lightbox.hidden) closeLightbox();
});

document.getElementById("lbSave").addEventListener("click", async () => {
  if (!currentItem) return;
  const btn = document.getElementById("lbSave");
  btn.disabled = true;
  btn.textContent = "Salvando…";
  const tags = document
    .getElementById("lbTags")
    .value.split(",")
    .map((t) => t.trim())
    .filter(Boolean);
  const notes = document.getElementById("lbNotes").value;
  try {
    await fetch(`/api/library/${currentItem.id}/tags`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tags }),
    });
    await fetch(`/api/library/${currentItem.id}/notes`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes }),
    });
    closeLightbox();
    await refreshAfterChange();
  } catch {
    alert("Não foi possível salvar as alterações.");
  } finally {
    btn.disabled = false;
    btn.textContent = "💾 Salvar";
  }
});

document.getElementById("lbCopyCredit").addEventListener("click", async () => {
  const text = document.getElementById("lbAttrib").textContent;
  try {
    await navigator.clipboard.writeText(text);
    flash("lbCopyCredit", "✓ Copiado!");
  } catch {
    /* ignore */
  }
});

document.getElementById("lbDelete").addEventListener("click", async () => {
  if (!currentItem) return;
  const item = currentItem;
  if (!confirm(`Remover “${item.title}” da biblioteca? O arquivo será apagado do HD.`)) return;
  try {
    await fetch(`/api/library/${item.id}`, { method: "DELETE" });
    closeLightbox();
    await refreshAfterChange();
  } catch {
    alert("Não foi possível remover.");
  }
});

// ---- Shared refresh ----
async function refreshAfterChange() {
  await loadTags();
  await loadCollections();
  await loadImages();
  updateLibCount();
}

// ---- Toolbar wiring ----
let searchTimer = null;
document.getElementById("search").addEventListener("input", (e) => {
  searchText = e.target.value.trim();
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadImages, 250);
});

document.getElementById("collectionFilter").addEventListener("change", (e) => {
  activeCollection = e.target.value;
  loadImages();
});

document.getElementById("newCollectionBtn").addEventListener("click", async () => {
  const name = prompt("Nome da nova coleção (ex.: Aula 3 - Revolução Francesa):");
  if (!name || !name.trim()) return;
  try {
    await fetch("/api/collections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim() }),
    });
    await loadCollections();
  } catch {
    alert("Não foi possível criar a coleção.");
  }
});

document.getElementById("exportCreditsBtn").addEventListener("click", async () => {
  const params = new URLSearchParams();
  if (activeTag) params.set("tag", activeTag);
  if (activeCollection) params.set("collection_id", activeCollection);
  if (searchText) params.set("q", searchText);
  const data = await (await fetch("/api/library?" + params.toString())).json();
  if (!data.results.length) return;
  const text = data.results
    .map((i) => i.attribution || `${i.title} — ${i.source} (${i.license || ""})`)
    .join("\n");
  try {
    await navigator.clipboard.writeText(text);
    flash("exportCreditsBtn", "✓ Copiado!");
  } catch {
    const blob = new Blob([text], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "creditos.txt";
    a.click();
  }
});

function flash(id, text) {
  const btn = document.getElementById(id);
  const old = btn.textContent;
  btn.textContent = text;
  setTimeout(() => (btn.textContent = old), 1400);
}

async function updateLibCount() {
  try {
    const data = await (await fetch("/api/library/refs")).json();
    document.getElementById("libCount").textContent = data.refs.length;
  } catch {
    /* ignore */
  }
}

// ---- Init ----
loadAll();
