let allListings = [];
let allSites = [];
let currentType = "";
const DEFAULT_SORT = { key: "title", direction: "asc" };
let sortState = { ...DEFAULT_SORT };

const $ = (id) => document.getElementById(id);
const NUMERIC_SORTS = new Set(["price", "weight_g", "price_per_g", "image", "available", "confidence"]);
const CONFIDENCE_RANK = { low: 1, medium: 2, high: 3 };

function currencyCode(value) {
  return value || "USD";
}

function money(value, currency = "USD") {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: currencyCode(currency) }).format(value);
}

function grams(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (value >= 1000) return `${(value / 1000).toFixed(3)} kg`;
  return `${Number(value).toFixed(value < 10 ? 2 : 1)} g`;
}

function pricePerG(value, currency = "USD") {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${money(value, currency)}/g`;
}

function normalize(value) {
  return String(value || "").toLowerCase();
}

function safeRemoteImageUrl(value) {
  if (!value || !/^https?:\/\//i.test(String(value))) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function prepareListing(item) {
  const imageUrl = safeRemoteImageUrl(item.image_url);
  return {
    ...item,
    _imageUrl: imageUrl,
    _searchText: normalize([
      item.title,
      item.source,
      item.meteorite_type,
      item.subtype,
      item.classification_text,
      item.url
    ].join(" ")),
    _titleSort: normalize(item.title)
  };
}

function isUnavailable(item) {
  return item.available === false;
}

function includeUnavailable() {
  return Boolean($("includeUnavailable")?.checked);
}

function isNonIndividualItem(item) {
  const title = normalize(item.title).trim();
  const url = normalize(item.url);
  const image = normalize(item.image_url);
  const genericTitles = new Set([
    "books",
    "book",
    "meteorites",
    "impactites",
    "minerals",
    "meteorite related rare minerals",
    "unclassified meteorites",
    "catalog",
    "catalogue",
    "publications",
    "gallery",
    "collection",
    "welcome to baitylia"
  ]);

  if (genericTitles.has(title)) return true;
  if (/\/(books?|minerals?|meteorites?|impactites?)(?:$|[?#])/.test(url) || /\/unclassified\.aspx(?:$|[?#])/.test(url)) return true;
  if (!item.price && !item.weight_g && /favicon|ajax-loader|logo|spinner|sold\.jpg|red(?:%20|\s)*dot/.test(image)) return true;
  return false;
}

function visibleBaseListings() {
  return allListings.filter((item) => !isNonIndividualItem(item) && (includeUnavailable() || !isUnavailable(item)));
}

function fillFilters() {
  const selectedType = $("typeFilter").value;
  const selectedSource = $("sourceFilter").value;
  const typeSet = new Set();
  const sourceSet = new Set();

  for (const item of visibleBaseListings()) {
    if (item.meteorite_type) typeSet.add(item.meteorite_type);
    if (item.source) sourceSet.add(item.source);
  }

  $("typeFilter").innerHTML = '<option value="">All types</option>';
  $("sourceFilter").innerHTML = '<option value="">All sources</option>';

  for (const type of [...typeSet].sort()) {
    const opt = document.createElement("option");
    opt.value = type;
    opt.textContent = type;
    $("typeFilter").appendChild(opt);
  }

  for (const source of [...sourceSet].sort()) {
    const opt = document.createElement("option");
    opt.value = source;
    opt.textContent = source;
    $("sourceFilter").appendChild(opt);
  }

  $("typeFilter").value = typeSet.has(selectedType) ? selectedType : "";
  $("sourceFilter").value = sourceSet.has(selectedSource) ? selectedSource : "";
  currentType = $("typeFilter").value;
  renderChips();
}

function renderChips(baseItems = visibleBaseListings()) {
  const counts = new Map();

  for (const item of baseItems) {
    const type = item.meteorite_type || "unknown";
    counts.set(type, (counts.get(type) || 0) + 1);
  }

  const chips = $("typeChips");
  chips.innerHTML = "";

  const all = document.createElement("button");
  all.textContent = `All (${baseItems.length})`;
  all.className = currentType === "" ? "active" : "";
  all.onclick = () => {
    currentType = "";
    $("typeFilter").value = "";
    render();
  };
  chips.appendChild(all);

  for (const [type, count] of [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    const btn = document.createElement("button");
    btn.textContent = `${type} (${count})`;
    btn.className = currentType === type ? "active" : "";
    btn.onclick = () => {
      currentType = type;
      $("typeFilter").value = type;
      render();
    };
    chips.appendChild(btn);
  }
}

function parseSort(value) {
  const [key, direction] = String(value || `${DEFAULT_SORT.key}:${DEFAULT_SORT.direction}`).split(":");
  return { key: key || DEFAULT_SORT.key, direction: direction === "desc" ? "desc" : "asc" };
}

function sortValue(item, key) {
  if (key === "image") return item._imageUrl ? 1 : 0;
  if (key === "title") return item._titleSort || normalize(item.title);
  if (key === "meteorite_type") return normalize(`${item.meteorite_type || "unknown"} ${item.subtype || ""} ${item.title || ""}`);
  if (key === "subtype") return normalize(`${item.subtype || ""} ${item.title || ""}`);
  if (key === "source") return normalize(`${item.source || ""} ${item.title || ""}`);
  if (key === "available") return isUnavailable(item) ? 0 : 1;
  if (key === "confidence") return CONFIDENCE_RANK[normalize(item.confidence)] || 0;
  return item[key];
}

function compareValues(aValue, bValue, numeric, direction) {
  const aMissing = aValue === null || aValue === undefined || Number.isNaN(aValue) || aValue === "";
  const bMissing = bValue === null || bValue === undefined || Number.isNaN(bValue) || bValue === "";
  if (aMissing && bMissing) return 0;
  if (aMissing) return 1;
  if (bMissing) return -1;

  const result = numeric
    ? Number(aValue) - Number(bValue)
    : String(aValue).localeCompare(String(bValue), undefined, { numeric: true, sensitivity: "base" });
  return direction === "desc" ? -result : result;
}

function compareListings(a, b) {
  const numeric = NUMERIC_SORTS.has(sortState.key);
  const result = compareValues(sortValue(a, sortState.key), sortValue(b, sortState.key), numeric, sortState.direction);
  if (result) return result;
  return normalize(a.title).localeCompare(normalize(b.title));
}

function updateSortHeaders() {
  document.querySelectorAll("th[data-sort]").forEach((th) => {
    const active = th.dataset.sort === sortState.key;
    const indicator = th.querySelector(".sort-indicator");
    th.setAttribute("aria-sort", active ? (sortState.direction === "asc" ? "ascending" : "descending") : "none");
    th.querySelector("button").classList.toggle("active", active);
    if (indicator) indicator.textContent = active ? (sortState.direction === "asc" ? "▲" : "▼") : "";
  });
}

function sortLabel(key, direction) {
  const labels = {
    image: "image",
    title: "meteorite name",
    meteorite_type: "type",
    subtype: "subtype",
    price: "price",
    weight_g: "weight",
    price_per_g: "$/g",
    source: "source",
    available: "status",
    confidence: "confidence"
  };
  return `Sort: ${labels[key] || key} ${direction === "desc" ? "descending" : "ascending"}`;
}

function setSort(key, direction) {
  sortState = { key, direction };
  const value = `${key}:${direction}`;
  const select = $("sortBy");
  if (![...select.options].some((option) => option.value === value)) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = sortLabel(key, direction);
    select.appendChild(option);
  }
  select.value = value;
  render();
}

function filteredListings(baseItems = visibleBaseListings()) {
  const q = normalize($("search").value);
  const type = $("typeFilter").value || currentType;
  const source = $("sourceFilter").value;

  const items = baseItems.filter((item) => {
    return (!q || item._searchText.includes(q)) &&
      (!type || item.meteorite_type === type) &&
      (!source || item.source === source);
  });

  items.sort(compareListings);
  return items;
}

function summarizePricePerG(items, mode) {
  const groups = new Map();
  for (const item of items) {
    if (item.available === false || typeof item.price_per_g !== "number") continue;
    const currency = currencyCode(item.currency);
    if (!groups.has(currency)) groups.set(currency, []);
    groups.get(currency).push(item.price_per_g);
  }

  if (!groups.size) return "—";
  if (groups.size > 1) {
    return [...groups.entries()].map(([currency, values]) => {
      const value = mode === "best" ? Math.min(...values) : values.reduce((a, b) => a + b, 0) / values.length;
      return pricePerG(value, currency);
    }).join(" / ");
  }

  const [[currency, values]] = [...groups.entries()];
  const value = mode === "best" ? Math.min(...values) : values.reduce((a, b) => a + b, 0) / values.length;
  return pricePerG(value, currency);
}

function updateSummary(items) {
  $("totalListings").textContent = items.length;
  $("totalSources").textContent = new Set(items.map((x) => x.source)).size;
  $("avgPricePerG").textContent = summarizePricePerG(items, "avg");
  $("bestDeal").textContent = summarizePricePerG(items, "best");
}

function renderSources() {
  const wrap = $("sourcesList");
  wrap.innerHTML = "";
  for (const site of [...allSites].sort((a, b) => Number(b.enabled !== false) - Number(a.enabled !== false) || normalize(a.name).localeCompare(normalize(b.name)))) {
    const card = document.createElement("article");
    card.className = "source-card";

    const title = document.createElement("a");
    title.href = site.base_url || site.inventory_urls?.[0] || "#";
    title.target = "_blank";
    title.rel = "noopener noreferrer";
    title.textContent = site.name || "Unnamed source";

    const status = document.createElement("span");
    status.className = `source-status ${site.enabled === false ? "disabled" : "enabled"}`;
    status.textContent = site.enabled === false ? "Disabled" : "Enabled";

    const heading = document.createElement("div");
    heading.className = "source-card-heading";
    heading.append(title, status);

    const description = document.createElement("p");
    description.textContent = site.description || site.notes || "No description provided.";

    const url = document.createElement("div");
    url.className = "source-url";
    url.textContent = site.base_url || "—";

    card.append(heading, description, url);
    wrap.appendChild(card);
  }
}

function render() {
  currentType = $("typeFilter").value || currentType;
  const baseItems = visibleBaseListings();
  const items = filteredListings(baseItems);
  const tbody = $("results");
  const tpl = $("rowTemplate");

  tbody.innerHTML = "";
  updateSummary(items);
  updateSortHeaders();
  renderChips(baseItems);

  if (!items.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="10" class="empty">No matching individual listings yet. Run the scraper or loosen the filters.</td>`;
    tbody.appendChild(tr);
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const item of items) {
    const row = tpl.content.cloneNode(true);
    const title = row.querySelector(".title");
    const thumb = row.querySelector(".thumb");
    const noImage = row.querySelector(".no-image");
    const imageUrl = item._imageUrl;

    if (imageUrl) {
      thumb.src = imageUrl;
      thumb.alt = `${item.title || "Meteorite listing"} image`;
      thumb.hidden = false;
      noImage.hidden = true;
    } else {
      thumb.removeAttribute("src");
      thumb.hidden = true;
      noImage.hidden = false;
    }

    title.textContent = item.title || "Untitled listing";
    title.href = item.url;
    row.querySelector(".classification").textContent = item.classification_text || "";
    row.querySelector(".type").textContent = item.meteorite_type || "unknown";
    row.querySelector(".subtype").textContent = item.subtype || "—";
    row.querySelector(".price").textContent = money(item.price, item.currency || "USD");
    row.querySelector(".weight").textContent = grams(item.weight_g);
    row.querySelector(".ppg").textContent = pricePerG(item.price_per_g, item.currency || "USD");
    row.querySelector(".source").textContent = item.source || "—";
    row.querySelector(".confidence").textContent = item.confidence || "—";
    const availability = row.querySelector(".availability");
    availability.textContent = isUnavailable(item) ? "Unavailable" : "Available";
    availability.classList.add(isUnavailable(item) ? "unavailable" : "available");
    fragment.appendChild(row);
  }
  tbody.appendChild(fragment);
}

async function init() {
  const [listingsResponse, sitesResponse] = await Promise.all([
    fetch("data/listings.json", { cache: "no-store" }),
    fetch("data/sites.json", { cache: "no-store" })
  ]);
  const data = await listingsResponse.json();
  allSites = await sitesResponse.json();
  allListings = (data.listings || []).map(prepareListing);
  $("updated").textContent = data.generated_at ? new Date(data.generated_at).toLocaleString() : "Not scraped yet";

  $("sortBy").value = `${DEFAULT_SORT.key}:${DEFAULT_SORT.direction}`;
  sortState = parseSort($("sortBy").value);
  fillFilters();
  renderSources();

  for (const id of ["search", "typeFilter", "sourceFilter"]) {
    $(id).addEventListener("input", () => {
      if (id === "typeFilter") currentType = $("typeFilter").value;
      render();
    });
  }

  $("sortBy").addEventListener("input", () => {
    sortState = parseSort($("sortBy").value);
    render();
  });

  $("includeUnavailable").addEventListener("change", () => {
    fillFilters();
    render();
  });

  document.querySelectorAll("th[data-sort] button").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.closest("th").dataset.sort;
      const direction = sortState.key === key && sortState.direction === "asc" ? "desc" : "asc";
      setSort(key, direction);
    });
  });

  render();
}

init().catch((err) => {
  console.error(err);
  $("updated").textContent = "Failed to load data";
});
