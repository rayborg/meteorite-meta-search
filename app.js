let allListings = [];
let currentType = "";
const $ = (id) => document.getElementById(id);

function money(value, currency = "USD") {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(value);
}

function grams(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (value >= 1000) return `${(value / 1000).toFixed(3)} kg`;
  return `${Number(value).toFixed(value < 10 ? 2 : 1)} g`;
}

function pricePerG(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `$${Number(value).toFixed(2)}/g`;
}

function normalize(value) {
  return String(value || "").toLowerCase();
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
    "collection"
  ]);

  if (genericTitles.has(title)) return true;
  if (/\/(books?|minerals?|meteorites?|impactites?|unclassified\.aspx)(?:$|[?#/])/.test(url)) return true;
  if (!item.price && !item.weight_g && /favicon|ajax-loader|logo|spinner/.test(image)) return true;
  return false;
}

function visibleBaseListings() {
  return allListings.filter((item) => !isNonIndividualItem(item));
}

function fillFilters() {
  const typeSet = new Set();
  const sourceSet = new Set();

  for (const item of visibleBaseListings()) {
    if (item.meteorite_type) typeSet.add(item.meteorite_type);
    if (item.source) sourceSet.add(item.source);
  }

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

  renderChips();
}

function renderChips() {
  const baseItems = visibleBaseListings();
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

function filteredListings() {
  const q = normalize($("search").value);
  const type = $("typeFilter").value || currentType;
  const source = $("sourceFilter").value;

  let items = visibleBaseListings().filter((item) => {
    const haystack = normalize([
      item.title,
      item.source,
      item.meteorite_type,
      item.subtype,
      item.classification_text,
      item.url
    ].join(" "));

    return (!q || haystack.includes(q)) &&
      (!type || item.meteorite_type === type) &&
      (!source || item.source === source);
  });

  const sortBy = $("sortBy").value;
  items.sort((a, b) => {
    if (sortBy === "price_per_g") return (a.price_per_g ?? Infinity) - (b.price_per_g ?? Infinity);
    if (sortBy === "price") return (a.price ?? Infinity) - (b.price ?? Infinity);
    if (sortBy === "weight_g_desc") return (b.weight_g ?? -1) - (a.weight_g ?? -1);
    if (sortBy === "source") return normalize(a.source).localeCompare(normalize(b.source)) || normalize(a.title).localeCompare(normalize(b.title));
    return normalize(`${a.meteorite_type} ${a.subtype} ${a.title}`).localeCompare(
      normalize(`${b.meteorite_type} ${b.subtype} ${b.title}`)
    );
  });

  return items;
}

function updateSummary(items) {
  $("totalListings").textContent = items.length;
  $("totalSources").textContent = new Set(items.map((x) => x.source)).size;

  const ppgs = items.map((x) => x.price_per_g).filter((x) => typeof x === "number");
  if (ppgs.length) {
    const avg = ppgs.reduce((a, b) => a + b, 0) / ppgs.length;
    const best = Math.min(...ppgs);
    $("avgPricePerG").textContent = pricePerG(avg);
    $("bestDeal").textContent = pricePerG(best);
  } else {
    $("avgPricePerG").textContent = "—";
    $("bestDeal").textContent = "—";
  }
}

function render() {
  currentType = $("typeFilter").value || currentType;
  const items = filteredListings();
  const tbody = $("results");
  const tpl = $("rowTemplate");

  tbody.innerHTML = "";
  updateSummary(items);
  renderChips();

  if (!items.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="8" class="empty">No matching individual listings yet. Run the scraper or loosen the filters.</td>`;
    tbody.appendChild(tr);
    return;
  }

  for (const item of items) {
    const row = tpl.content.cloneNode(true);
    const title = row.querySelector(".title");
    title.textContent = item.title || "Untitled listing";
    title.href = item.url;
    row.querySelector(".classification").textContent = item.classification_text || "";
    row.querySelector(".type").textContent = item.meteorite_type || "unknown";
    row.querySelector(".subtype").textContent = item.subtype || "—";
    row.querySelector(".price").textContent = money(item.price, item.currency || "USD");
    row.querySelector(".weight").textContent = grams(item.weight_g);
    row.querySelector(".ppg").textContent = pricePerG(item.price_per_g);
    row.querySelector(".source").textContent = item.source || "—";
    row.querySelector(".confidence").textContent = item.confidence || "—";
    tbody.appendChild(row);
  }
}

async function init() {
  const response = await fetch("data/listings.json", { cache: "no-store" });
  const data = await response.json();
  allListings = data.listings || [];
  $("updated").textContent = data.generated_at ? new Date(data.generated_at).toLocaleString() : "Not scraped yet";

  fillFilters();

  for (const id of ["search", "typeFilter", "sourceFilter", "sortBy"]) {
    $(id).addEventListener("input", () => {
      if (id === "typeFilter") currentType = $("typeFilter").value;
      render();
    });
  }

  render();
}

init().catch((err) => {
  console.error(err);
  $("updated").textContent = "Failed to load data";
});
