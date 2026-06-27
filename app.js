let allListings = [];
let allSites = [];
let currentType = "";
let currentSubtype = "";
let expandedType = "";
const DEFAULT_SORT = { key: "title", direction: "asc" };
let sortState = { ...DEFAULT_SORT };
let priceDistributionFilter = null;
let selectedSourceGroupKey = "";

const $ = (id) => document.getElementById(id);
const NUMERIC_SORTS = new Set(["price", "weight_g", "price_per_g", "image", "available", "confidence"]);
const CONFIDENCE_RANK = { low: 1, medium: 2, high: 3 };
const UNSPECIFIED_SUBTYPE = "__unspecified__";
const HEAVY_PRICE_PER_KG_WEIGHT_G = 1000;
const PRICE_DISTRIBUTION_MAX_GROUPS = 24;
const PRICE_DISTRIBUTION_BUCKETS = 8;
const OTHER_METEORITE_LABEL = "Other meteorite";
const SOURCE_STATUS_GROUPS = [
  { key: "enabled", label: "Connected", detailLabel: "Connected Sources", ariaLabel: "Connected or enabled sources" },
  { key: "parserStart", label: "Parser starts", detailLabel: "Disabled Parser Starts", ariaLabel: "Disabled parser starts" },
  { key: "backlog", label: "Backlog", detailLabel: "Disabled Backlog Sources", ariaLabel: "Disabled backlog sources" },
  { key: "policyBlocked", label: "Policy/ref", detailLabel: "Policy And Reference Sources", ariaLabel: "Policy-blocked or reference sources" }
];
const CATEGORY_ALIASES = new Map([
  ["stone", "unknown"]
]);
const CATEGORY_LABELS = new Map([
  ["ordinary chondrite", "Ordinary chondrites"],
  ["carbonaceous chondrite", "Carbonaceous chondrites"],
  ["achondrite", "Achondrites"],
  ["lunar", "Lunar meteorites"],
  ["martian", "Martian meteorites"],
  ["iron", "Iron meteorites"],
  ["pallasite", "Pallasites"],
  ["mesosiderite", "Mesosiderites"],
  ["chondrite", "Other chondrites"],
  ["tektite/impactite", "Tektites & impactites"],
  ["unknown", "Unclassified / unknown"]
]);
const TYPE_ORDER = [
  "ordinary chondrite",
  "carbonaceous chondrite",
  "chondrite",
  "achondrite",
  "lunar",
  "martian",
  "iron",
  "pallasite",
  "mesosiderite",
  "tektite/impactite",
  "unknown"
];
const SUBTYPE_LABELS = new Map([
  ["ACAPULCOITE", "Acapulcoite"],
  ["LODRANITE", "Lodranite"],
  ["WINONAITE", "Winonaite"],
  ["AUBRITE", "Aubrite"],
  ["UREILITE", "Ureilite"],
  ["ANGRITE", "Angrite"],
  ["BRACHINITE", "Brachinite"],
  ["HOWARDITE", "Howardite"],
  ["EUCRITE", "Eucrite"],
  ["EUC", "Eucrite"],
  ["DIOGENITE", "Diogenite"],
  ["ACHONDRITE-UNG", "Ungrouped achondrite"],
  ["ACHONDRITE", "Achondrite"],
  ["SHERGOTTITE", "Shergottite"],
  ["NAKHLITE", "Nakhlite"],
  ["CHASSIGNITE", "Chassignite"],
  ["OCTAHEDRITE", "Octahedrite"],
  ["HEXAHEDRITE", "Hexahedrite"],
  ["ATAXITE", "Ataxite"],
  ["IRUNGR", "Ungrouped iron"],
  ["PALLASITE", "Pallasite"],
  ["MESOSIDERITE", "Mesosiderite"],
  ["L-MELTBRECCIA", "L-melt breccia"]
]);
const SUBTYPE_ORDER = new Map([
  ["CI", 10], ["C2", 20], ["CM", 30], ["CO", 40], ["CV", 50], ["CVRED", 51], ["CVOXA", 52],
  ["CK", 60], ["CR", 70], ["CH", 80], ["CBA", 90], ["CBB", 91], ["CB", 92],
  ["H", 110], ["L", 210], ["LL", 310], ["H/L", 405], ["H/L3", 406], ["L(LL)", 410], ["L(LL)3", 411],
  ["OC", 490], ["L-MELTBRECCIA", 500],
  ["EH", 610], ["EL", 620], ["R", 630],
  ["ACAPULCOITE", 710], ["LODRANITE", 720], ["WINONAITE", 730], ["AUBRITE", 740], ["UREILITE", 750],
  ["ANGRITE", 760], ["BRACHINITE", 770], ["HED", 780], ["HOWARDITE", 790], ["EUCRITE", 800],
  ["EUC", 801], ["DIOGENITE", 810], ["ACHONDRITE-UNG", 850], ["ACHONDRITE", 860],
  ["SHERGOTTITE", 910], ["NAKHLITE", 920], ["CHASSIGNITE", 930],
  ["IAB", 1010], ["IIA", 1020], ["IIAB", 1030], ["IIIAB", 1040], ["IVA", 1050], ["IVB", 1060],
  ["IIE", 1070], ["IRUNGR", 1080], ["IC", 1090], ["OCTAHEDRITE", 1100], ["HEXAHEDRITE", 1110],
  ["ATAXITE", 1120], ["PALLASITE", 1210], ["MESOSIDERITE", 1310]
]);

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

function pricePerKg(value, currency = "USD") {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${money(value * 1000, currency)}/kg`;
}

function usdPriceValue(item) {
  if (Number.isFinite(item.price_usd)) return item.price_usd;
  return currencyCode(item.currency) === "USD" && Number.isFinite(item.price) ? item.price : null;
}

function usdPricePerGValue(item) {
  if (Number.isFinite(item.price_per_g_usd)) return item.price_per_g_usd;
  return currencyCode(item.currency) === "USD" && Number.isFinite(item.price_per_g) ? item.price_per_g : null;
}

function pricePerGDisplay(item) {
  const value = usdPricePerGValue(item);
  if (!Number.isFinite(value)) return "—";
  const perG = pricePerG(value, "USD");
  return Number.isFinite(item.weight_g) && item.weight_g >= HEAVY_PRICE_PER_KG_WEIGHT_G
    ? `${perG} (${pricePerKg(value, "USD")})`
    : perG;
}

function verifiedDateLabel(value) {
  if (!value) return "Not verified";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Verified date unknown";
  return `Verified ${date.toLocaleDateString()}`;
}

function originalPriceLabel(item) {
  const currency = currencyCode(item.currency);
  if (currency === "USD" || !Number.isFinite(item.price)) return "";
  const parts = [`Original price: ${money(item.price, currency)}`];
  if (Number.isFinite(item.fx_rate_to_usd) && item.fx_rate_date) {
    parts.push(`FX: ${item.fx_rate_to_usd} USD/${currency} on ${item.fx_rate_date}`);
  }
  return parts.join("; ");
}

function normalize(value) {
  return String(value || "").toLowerCase();
}

function titleCaseLabel(value) {
  return String(value || "").toLowerCase().replace(/\b[a-z]/g, (letter) => letter.toUpperCase());
}

function categoryKey(value) {
  const key = normalize(value).trim();
  return CATEGORY_ALIASES.get(key) || key || "unknown";
}

function categoryLabel(value) {
  const key = categoryKey(value);
  return CATEGORY_LABELS.get(key) || titleCaseLabel(key);
}

function itemCategoryKey(item) {
  return categoryKey(item.meteorite_type);
}

function subtypeKey(value) {
  return value ? String(value) : UNSPECIFIED_SUBTYPE;
}

function subtypeOrderToken(value) {
  return String(value || "").toUpperCase().replace(/\s+/g, "");
}

function subtypeCodeLabel(value) {
  const token = subtypeOrderToken(value);
  const cvMatch = token.match(/^CV(OXA|RED)(\d(?:\.\d)?)?$/);
  if (cvMatch) return `CV${cvMatch[1] === "OXA" ? "oxA" : "red"}${cvMatch[2] || ""}`;
  const cbMatch = token.match(/^CB([AB])(\d(?:\.\d)?)?$/);
  if (cbMatch) return `CB${cbMatch[1] === "A" ? "a" : "b"}${cbMatch[2] || ""}`;
  if (/^(?:H|L|LL|EH|EL|R)\d(?:\.\d)?(?:[-/]\d(?:\.\d)?)?$/.test(token)) return token;
  if (/^L\(LL\)\d(?:[-/]\d)?$/.test(token)) return token;
  if (/^(?:CI|CM|CO|CV|CK|CR|CH|CB|CBA|CBB|C2)\d?(?:\.\d)?$/.test(token)) return token;
  if (/^(?:IAB|IIA|IIAB|IIIAB|IVA|IVB|IIE|IC|HED|OC)$/.test(token)) return token;
  return "";
}

function subtypeLabel(value) {
  if (value === UNSPECIFIED_SUBTYPE || !String(value || "").trim()) return "No subtype recorded";
  const raw = String(value).trim().replace(/\s+/g, " ");
  const token = subtypeOrderToken(raw);
  if (SUBTYPE_LABELS.has(token)) return SUBTYPE_LABELS.get(token);
  return subtypeCodeLabel(raw) || (/^[A-Z][A-Z\s/-]+$/.test(raw) ? titleCaseLabel(raw.replace(/-/g, " ")) : raw);
}

function subtypeDisplayLabel(value) {
  return value ? subtypeLabel(value) : "—";
}

function subtypeRank(value) {
  if (value === UNSPECIFIED_SUBTYPE) return 100000;
  const token = subtypeOrderToken(value);
  if (!token) return 99999;
  if (SUBTYPE_ORDER.has(token)) return SUBTYPE_ORDER.get(token);

  let match = token.match(/^(CVRED|CVOXA|CI|CM|CO|CV|CK|CR|CH|CB)(\d(?:\.\d)?)?/);
  if (match && SUBTYPE_ORDER.has(match[1])) return SUBTYPE_ORDER.get(match[1]) + Number(match[2] || 0);

  match = token.match(/^(H|L|LL)(\d(?:\.\d)?)(?:[/\-](\d(?:\.\d)?))?/);
  if (match && SUBTYPE_ORDER.has(match[1])) return SUBTYPE_ORDER.get(match[1]) + Number(match[2]);

  match = token.match(/^(EH|EL|R)(\d(?:\.\d)?)(?:[/\-](\d(?:\.\d)?))?/);
  if (match && SUBTYPE_ORDER.has(match[1])) return SUBTYPE_ORDER.get(match[1]) + Number(match[2]);

  return 99998;
}

function compareTypes(a, b) {
  const aKey = categoryKey(a);
  const bKey = categoryKey(b);
  const aRank = TYPE_ORDER.indexOf(aKey);
  const bRank = TYPE_ORDER.indexOf(bKey);
  const rankDiff = (aRank === -1 ? TYPE_ORDER.length : aRank) - (bRank === -1 ? TYPE_ORDER.length : bRank);
  return rankDiff || categoryLabel(aKey).localeCompare(categoryLabel(bKey), undefined, { numeric: true, sensitivity: "base" });
}

function compareSubtypes(a, b) {
  return subtypeRank(a) - subtypeRank(b) ||
    subtypeLabel(a).localeCompare(subtypeLabel(b), undefined, { numeric: true, sensitivity: "base" });
}

function controlId(prefix, value) {
  const slug = normalize(value).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "unknown";
  return `${prefix}-${slug}`;
}

function matchesSubtype(item, subtype) {
  if (!subtype) return true;
  return subtype === UNSPECIFIED_SUBTYPE ? !item.subtype : item.subtype === subtype;
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

function imageCandidates(item) {
  const rawValues = [
    item.image_url,
    ...(Array.isArray(item.image_urls) ? item.image_urls : [])
  ];
  const urls = [];
  const seen = new Set();

  for (const value of rawValues) {
    const url = safeRemoteImageUrl(value);
    if (url && !seen.has(url)) {
      urls.push(url);
      seen.add(url);
    }
  }

  return urls;
}

function showNoImage(thumb, noImage) {
  thumb.removeAttribute("src");
  thumb.hidden = true;
  noImage.hidden = false;
}

function showImageAtIndex(thumb, noImage, item, index = 0) {
  const urls = item._imageUrls || [];
  const imageUrl = urls[index];

  if (!imageUrl) {
    showNoImage(thumb, noImage);
    return;
  }

  thumb.addEventListener("error", () => showImageAtIndex(thumb, noImage, item, index + 1), { once: true });
  thumb.src = imageUrl;
  thumb.alt = `${item.title || "Meteorite listing"} image`;
  thumb.hidden = false;
  noImage.hidden = true;
}

function prepareListing(item) {
  const imageUrls = imageCandidates(item);
  const imageUrl = imageUrls[0] || null;
  return {
    ...item,
    _imageUrl: imageUrl,
    _imageUrls: imageUrls,
    _searchText: normalize([
      item.title,
      item.canonical_name,
      item.canonical_name_display,
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
  const selectedTypeValue = $("typeFilter").value || currentType;
  const selectedType = selectedTypeValue ? categoryKey(selectedTypeValue) : "";
  const selectedSource = $("sourceFilter").value;
  const typeSet = new Set();
  const sourceSet = new Set();

  for (const item of visibleBaseListings()) {
    typeSet.add(itemCategoryKey(item));
    if (item.source) sourceSet.add(item.source);
  }

  $("typeFilter").innerHTML = '<option value="">All categories</option>';
  $("sourceFilter").innerHTML = '<option value="">All sources</option>';

  for (const type of [...typeSet].sort(compareTypes)) {
    const opt = document.createElement("option");
    opt.value = type;
    opt.textContent = categoryLabel(type);
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
  if (!currentType) currentSubtype = "";
  if (expandedType && expandedType !== currentType && !typeSet.has(expandedType)) expandedType = "";
  renderChips();
}

function chipCountListings(baseItems = visibleBaseListings()) {
  const q = normalize($("search")?.value).trim();
  const source = $("sourceFilter")?.value;
  return baseItems.filter((item) => {
    return (!q || item._searchText.includes(q)) &&
      (!source || item.source === source);
  });
}

function renderChips(baseItems = chipCountListings()) {
  const counts = new Map();
  const subtypeCounts = new Map();

  for (const item of baseItems) {
    const type = itemCategoryKey(item);
    counts.set(type, (counts.get(type) || 0) + 1);
    if (!subtypeCounts.has(type)) subtypeCounts.set(type, new Map());
    const subtype = subtypeKey(item.subtype);
    const typeSubtypeCounts = subtypeCounts.get(type);
    typeSubtypeCounts.set(subtype, (typeSubtypeCounts.get(subtype) || 0) + 1);
  }
  if (currentType && !counts.has(currentType)) counts.set(currentType, 0);
  if (currentType) {
    if (!subtypeCounts.has(currentType)) subtypeCounts.set(currentType, new Map());
    if (currentSubtype) {
      const typeSubtypeCounts = subtypeCounts.get(currentType);
      if (!typeSubtypeCounts.has(currentSubtype)) typeSubtypeCounts.set(currentSubtype, 0);
    }
  }

  const chips = $("typeChips");
  chips.innerHTML = "";

  const all = document.createElement("button");
  const allActive = currentType === "";
  all.type = "button";
  all.textContent = `All categories (${baseItems.length})`;
  all.className = allActive ? "active" : "";
  all.setAttribute("aria-pressed", String(allActive));
  all.onclick = () => {
    clearPriceDistributionFilter();
    currentType = "";
    currentSubtype = "";
    expandedType = "";
    $("typeFilter").value = "";
    render();
  };
  chips.appendChild(all);

  for (const [type, count] of [...counts.entries()].sort((a, b) => compareTypes(a[0], b[0]))) {
    const group = document.createElement("div");
    const listId = controlId("subtypes", type);
    const typeLabel = categoryLabel(type);
    const btn = document.createElement("button");
    const active = currentType === type;
    const expanded = expandedType === type;
    btn.type = "button";
    btn.textContent = `${typeLabel} (${count})`;
    btn.className = `category-chip${active ? " active" : ""}`;
    btn.setAttribute("aria-pressed", String(active));
    btn.setAttribute("aria-expanded", String(expanded));
    btn.setAttribute("aria-controls", listId);
    btn.onclick = () => {
      clearPriceDistributionFilter();
      expandedType = expanded ? "" : type;
      currentType = type;
      currentSubtype = "";
      $("typeFilter").value = type;
      render();
    };
    group.className = `category-group${active ? " active" : ""}`;
    group.appendChild(btn);

    if (expanded) {
      const subtypeList = document.createElement("div");
      const typeSubtypeCounts = subtypeCounts.get(type) || new Map();
      const unspecified = typeSubtypeCounts.has(UNSPECIFIED_SUBTYPE)
        ? [[UNSPECIFIED_SUBTYPE, typeSubtypeCounts.get(UNSPECIFIED_SUBTYPE)]]
        : [];
      const subtypeEntries = [...typeSubtypeCounts.entries()]
        .filter(([subtype]) => subtype !== UNSPECIFIED_SUBTYPE)
        .sort((a, b) => compareSubtypes(a[0], b[0]));
      if (unspecified.length) {
        subtypeEntries.push(unspecified[0]);
      }

      subtypeList.id = listId;
      subtypeList.className = "subtype-list";
      subtypeList.setAttribute("role", "group");
      subtypeList.setAttribute("aria-label", `${typeLabel} subtype filters`);

      if (type === "tektite/impactite") {
        const helper = document.createElement("p");
        helper.id = `${listId}-note`;
        helper.className = "category-helper";
        helper.textContent = "Includes tektites and related impact material; not a formal meteorite category.";
        subtypeList.setAttribute("aria-describedby", helper.id);
        subtypeList.appendChild(helper);
      }

      const allType = document.createElement("button");
      const allTypeActive = currentType === type && !currentSubtype;
      allType.type = "button";
      allType.textContent = `All ${typeLabel} (${count})`;
      allType.className = allTypeActive ? "subtype-chip active" : "subtype-chip";
      allType.setAttribute("aria-pressed", String(allTypeActive));
      allType.onclick = () => {
        clearPriceDistributionFilter();
        currentType = type;
        currentSubtype = "";
        expandedType = type;
        $("typeFilter").value = type;
        render();
      };
      subtypeList.appendChild(allType);

      for (const [subtype, subtypeCount] of subtypeEntries) {
        const subtypeButton = document.createElement("button");
        const subtypeActive = currentType === type && currentSubtype === subtype;
        subtypeButton.type = "button";
        subtypeButton.textContent = `${subtypeLabel(subtype)} (${subtypeCount})`;
        subtypeButton.className = subtypeActive ? "subtype-chip active" : "subtype-chip";
        subtypeButton.setAttribute("aria-pressed", String(subtypeActive));
        subtypeButton.onclick = () => {
          clearPriceDistributionFilter();
          currentType = type;
          currentSubtype = subtype;
          expandedType = type;
          $("typeFilter").value = type;
          render();
        };
        subtypeList.appendChild(subtypeButton);
      }
      group.appendChild(subtypeList);
    }

    chips.appendChild(group);
  }
}

function parseSort(value) {
  const [key, direction] = String(value || `${DEFAULT_SORT.key}:${DEFAULT_SORT.direction}`).split(":");
  return { key: key || DEFAULT_SORT.key, direction: direction === "desc" ? "desc" : "asc" };
}

function sortValue(item, key) {
  if (key === "image") return item._imageUrl ? 1 : 0;
  if (key === "title") return item._titleSort || normalize(item.title);
  if (key === "meteorite_type") return normalize(`${itemCategoryKey(item)} ${item.subtype || ""} ${item.title || ""}`);
  if (key === "subtype") return normalize(`${item.subtype || ""} ${item.title || ""}`);
  if (key === "source") return normalize(`${item.source || ""} ${item.title || ""}`);
  if (key === "available") return isUnavailable(item) ? 0 : 1;
  if (key === "confidence") return CONFIDENCE_RANK[normalize(item.confidence)] || 0;
  if (key === "price") return usdPriceValue(item);
  if (key === "price_per_g") return usdPricePerGValue(item);
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
    meteorite_type: "category",
    subtype: "subtype",
    price: "price (USD)",
    weight_g: "weight",
    price_per_g: "price/g (USD)",
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
  const q = normalize($("search").value).trim();
  const type = currentType;
  const subtype = currentSubtype;
  const source = $("sourceFilter").value;

  const items = baseItems.filter((item) => {
    return (!q || item._searchText.includes(q)) &&
      (!type || itemCategoryKey(item) === type) &&
      (!subtype || matchesSubtype(item, subtype)) &&
      (!source || item.source === source);
  });

  items.sort(compareListings);
  return items;
}

function clearPriceDistributionFilter() {
  priceDistributionFilter = null;
}

function summarizePricePerG(items, mode) {
  const values = [];
  for (const item of items) {
    const value = usdPricePerGValue(item);
    if (!isUnavailable(item) && Number.isFinite(value)) values.push(value);
  }

  if (!values.length) return "—";
  const value = mode === "best" ? Math.min(...values) : values.reduce((a, b) => a + b, 0) / values.length;
  return pricePerG(value, "USD");
}

function hasPricePerGScope(items) {
  const q = normalize($("search").value).trim();
  const type = currentType;
  const source = $("sourceFilter").value;
  if (q || type || currentSubtype || source) return true;

  const titles = new Set(items.map((item) => normalize(item.title).trim()).filter(Boolean));
  return titles.size === 1;
}

function setPriceSummary(id, value, isMessage = false) {
  const element = $(id);
  element.textContent = value;
  element.classList.toggle("summary-message", isMessage);
}

function updateSummary(items) {
  $("totalListings").textContent = items.length;
  updateSourceSummary();
  if (!hasPricePerGScope(items)) {
    setPriceSummary("avgPricePerG", "Filter by category/source/search to compare price/g", true);
    setPriceSummary("bestDeal", "Narrow results to show lowest price/g", true);
    return;
  }

  setPriceSummary("avgPricePerG", summarizePricePerG(items, "avg"));
  setPriceSummary("bestDeal", summarizePricePerG(items, "best"));
}

function meteoriteGroupKey(item) {
  const canonical = normalize(item.canonical_name).trim();
  if (item.canonical_name_status === "metbull_verified" && canonical) return `canonical:${canonical}`;
  return "other-meteorite";
}

function meteoriteGroupLabel(item) {
  if (item.canonical_name_status === "metbull_verified") {
    return item.canonical_name_display || item.canonical_name || OTHER_METEORITE_LABEL;
  }
  return OTHER_METEORITE_LABEL;
}

function collectPriceDistributionGroups(items) {
  const groups = new Map();
  for (const item of items) {
    if (isUnavailable(item)) continue;
    const price = usdPricePerGValue(item);
    if (!Number.isFinite(price)) continue;

    const key = meteoriteGroupKey(item);
    if (!groups.has(key)) {
      groups.set(key, { key, label: meteoriteGroupLabel(item), values: [], sources: new Set() });
    }
    const group = groups.get(key);
    group.values.push(price);
    if (item.source) group.sources.add(item.source);
  }

  return [...groups.values()].sort((a, b) =>
    b.values.length - a.values.length ||
    a.label.localeCompare(b.label, undefined, { numeric: true, sensitivity: "base" })
  );
}

function priceDistributionRangeLabel(filter) {
  return `${pricePerG(filter.min, "USD")} to ${pricePerG(filter.max, "USD")}`;
}

function matchesPriceDistributionFilter(item, filter = priceDistributionFilter) {
  if (!filter || isUnavailable(item) || meteoriteGroupKey(item) !== filter.groupKey) return false;
  const value = usdPricePerGValue(item);
  if (!Number.isFinite(value)) return false;
  return value >= filter.min && (filter.isLast ? value <= filter.max : value < filter.max);
}

function reconcilePriceDistributionFilter(scopeItems) {
  if (!priceDistributionFilter) return;
  if (!scopeItems.some((item) => matchesPriceDistributionFilter(item))) {
    clearPriceDistributionFilter();
  }
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function average(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function appendPriceStat(parent, label, value) {
  const stat = document.createElement("div");
  const statLabel = document.createElement("span");
  const statValue = document.createElement("strong");
  stat.className = "price-stat";
  statLabel.textContent = label;
  statValue.textContent = pricePerG(value, "USD");
  stat.append(statLabel, statValue);
  parent.appendChild(stat);
}

function priceDistributionBuckets(values) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return [{ min, max, count: values.length, index: 0, isLast: true }];

  const bucketCount = Math.min(PRICE_DISTRIBUTION_BUCKETS, Math.max(2, values.length));
  const span = max - min;
  const buckets = Array.from({ length: bucketCount }, (_, index) => {
    const start = min + (span * index) / bucketCount;
    const end = min + (span * (index + 1)) / bucketCount;
    return { min: start, max: end, count: 0, index, isLast: index === bucketCount - 1 };
  });

  for (const value of values) {
    const index = Math.min(bucketCount - 1, Math.floor(((value - min) / span) * bucketCount));
    buckets[index].count += 1;
  }

  return buckets;
}

function setPriceDistributionFilter(group, bucket) {
  const active = priceDistributionFilter &&
    priceDistributionFilter.groupKey === group.key &&
    priceDistributionFilter.bucketIndex === bucket.index &&
    priceDistributionFilter.min === bucket.min &&
    priceDistributionFilter.max === bucket.max;
  if (active) {
    clearPriceDistributionFilter();
  } else {
    priceDistributionFilter = {
      groupKey: group.key,
      groupLabel: group.label,
      min: bucket.min,
      max: bucket.max,
      bucketIndex: bucket.index,
      isLast: bucket.isLast
    };
  }
  render();
}

function renderPriceChart(group) {
  const values = group.values;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const avg = average(values);
  const med = median(values);
  const sourceCount = group.sources.size;
  const card = document.createElement("article");
  const heading = document.createElement("div");
  const title = document.createElement("h3");
  const meta = document.createElement("span");
  const stats = document.createElement("div");
  const bars = document.createElement("div");
  const axis = document.createElement("div");
  const minLabel = document.createElement("span");
  const maxLabel = document.createElement("span");

  card.className = "price-chart-card";
  heading.className = "price-chart-heading";
  title.textContent = group.label;
  meta.className = "price-chart-meta";
  meta.textContent = `${values.length} priced ${values.length === 1 ? "listing" : "listings"} · ${sourceCount || 0} ${sourceCount === 1 ? "source" : "sources"}`;
  heading.append(title, meta);

  stats.className = "price-stat-grid";
  appendPriceStat(stats, "Min", min);
  appendPriceStat(stats, "Median", med);
  appendPriceStat(stats, "Avg", avg);
  appendPriceStat(stats, "Max", max);

  const buckets = priceDistributionBuckets(values);
  const maxBucketCount = Math.max(...buckets.map((bucket) => bucket.count), 1);
  bars.className = "price-bars";
  bars.setAttribute("role", "group");
  bars.setAttribute("aria-label", `${group.label} USD price per gram distribution`);

  for (const bucket of buckets) {
    const bar = document.createElement("button");
    const fill = document.createElement("span");
    const height = bucket.count ? Math.max(8, Math.round((bucket.count / maxBucketCount) * 100)) : 2;
    const active = priceDistributionFilter &&
      priceDistributionFilter.groupKey === group.key &&
      priceDistributionFilter.bucketIndex === bucket.index &&
      priceDistributionFilter.min === bucket.min &&
      priceDistributionFilter.max === bucket.max;
    bar.className = "price-bar";
    bar.type = "button";
    bar.disabled = bucket.count === 0;
    bar.title = `${bucket.count} ${bucket.count === 1 ? "listing" : "listings"}: ${pricePerG(bucket.min, "USD")} to ${pricePerG(bucket.max, "USD")}`;
    bar.setAttribute("aria-pressed", String(Boolean(active)));
    bar.setAttribute("aria-label", `${active ? "Clear" : "Filter"} ${group.label} listings ${active ? "from" : "to"} ${priceDistributionRangeLabel(bucket)}; ${bucket.count} ${bucket.count === 1 ? "listing" : "listings"}`);
    bar.onclick = () => setPriceDistributionFilter(group, bucket);
    fill.style.height = `${height}%`;
    bar.appendChild(fill);
    bars.appendChild(bar);
  }

  axis.className = "price-axis";
  minLabel.textContent = pricePerG(min, "USD");
  maxLabel.textContent = pricePerG(max, "USD");
  axis.append(minLabel, maxLabel);
  card.append(heading, stats, bars, axis);
  return card;
}

function renderPriceDistributionFilterControl(tableCount) {
  const container = $("priceDistributionFilter");
  if (!container) return;

  container.innerHTML = "";
  if (!priceDistributionFilter) {
    container.hidden = true;
    return;
  }

  const text = document.createElement("span");
  const clear = document.createElement("button");
  text.textContent = `Price range filter active: ${priceDistributionFilter.groupLabel}, ${priceDistributionRangeLabel(priceDistributionFilter)} (${tableCount} ${tableCount === 1 ? "listing" : "listings"} shown).`;
  clear.type = "button";
  clear.textContent = "Clear price range filter";
  clear.onclick = () => {
    clearPriceDistributionFilter();
    render();
  };
  container.append(text, clear);
  container.hidden = false;
}

function renderPriceDistribution(items) {
  const section = $("priceDistribution");
  const summary = $("priceDistributionSummary");
  const charts = $("priceDistributionCharts");
  if (!section || !summary || !charts) return;

  const q = normalize($("search")?.value).trim();
  charts.innerHTML = "";
  if (!q) {
    section.hidden = true;
    clearPriceDistributionFilter();
    return;
  }

  section.hidden = false;
  const groups = collectPriceDistributionGroups(items);
  const listingCount = groups.reduce((count, group) => count + group.values.length, 0);
  if (!groups.length) {
    summary.textContent = "No available matching listings have USD price/g data for a distribution chart.";
    return;
  }

  if (groups.length > PRICE_DISTRIBUTION_MAX_GROUPS) {
    summary.textContent = `Search matches ${groups.length} MetBull meteorite groups with USD price/g data across ${listingCount} available listings. Refine the search to ${PRICE_DISTRIBUTION_MAX_GROUPS} or fewer groups to generate one chart for each group.`;
    const empty = document.createElement("div");
    empty.className = "price-chart-empty";
    empty.textContent = "The current search is too broad for one chart per MetBull meteorite group.";
    charts.appendChild(empty);
    return;
  }

  summary.textContent = `Showing USD price/g distribution for ${groups.length} MetBull ${groups.length === 1 ? "meteorite group" : "meteorite groups"} across ${listingCount} available priced ${listingCount === 1 ? "listing" : "listings"}.`;
  const fragment = document.createDocumentFragment();
  for (const group of groups) {
    fragment.appendChild(renderPriceChart(group));
  }
  charts.appendChild(fragment);
}

function setSourcesPanelOpen(open) {
  $("sourcesPanel").hidden = !open;
  $("sourcesSummary").setAttribute("aria-expanded", String(open));
}

function openSourcesPanel() {
  setSourcesPanelOpen(true);
  const heading = $("sourcesHeading");
  const select = $("sourceInfoSelect");
  const focusTarget = select && !select.disabled ? select : heading;
  const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const behavior = reduceMotion ? "auto" : "smooth";
  heading.scrollIntoView({ behavior, block: "start" });
  try {
    focusTarget.focus({ preventScroll: true });
  } catch {
    focusTarget.focus();
  }
}

function siteIsEnabled(site) {
  return site.enabled !== false;
}

function sourceStage(site) {
  if (siteIsEnabled(site)) {
    return { key: "enabled", label: "Enabled", cardClass: "enabled", statusClass: "enabled" };
  }
  if (site.stage === "disabled_policy_blocked") {
    return { key: "policyBlocked", label: "Policy blocked", cardClass: "disabled", statusClass: "disabled" };
  }
  if (site.stage === "disabled_backlog") {
    return { key: "backlog", label: "Disabled backlog", cardClass: "disabled", statusClass: "backlog" };
  }
  if (site.stage === "disabled_parser_start") {
    return { key: "parserStart", label: "Disabled parser start", cardClass: "disabled", statusClass: "parser-start" };
  }
  return { key: "backlog", label: "Disabled backlog", cardClass: "disabled", statusClass: "backlog" };
}

function sourceStatusCounts() {
  const counts = {
    enabled: 0,
    total: allSites.length,
    parserStart: 0,
    backlog: 0,
    policyBlocked: 0
  };

  for (const site of allSites) {
    if (siteIsEnabled(site)) {
      counts.enabled += 1;
    }

    if (site.stage === "disabled_parser_start") counts.parserStart += 1;
    if (site.stage === "disabled_backlog") counts.backlog += 1;
    if (site.stage === "disabled_policy_blocked") counts.policyBlocked += 1;
  }

  return counts;
}


function sourceGroupConfig(key) {
  return SOURCE_STATUS_GROUPS.find((group) => group.key === key) || SOURCE_STATUS_GROUPS[0];
}


function sortedSourceEntries(sites = allSites) {
  return sites
    .map((site, index) => ({ site, index }))
    .sort((a, b) => (a.site.name || "").localeCompare(b.site.name || "", undefined, { numeric: true, sensitivity: "base" }));
}


function sourceGroupEntries(key) {
  return sortedSourceEntries(allSites).filter(({ site }) => sourceStage(site).key === key);
}


function renderSourceGroup(key) {
  const detail = $("sourceInfoDetail");
  const group = sourceGroupConfig(key);
  const entries = sourceGroupEntries(key);

  detail.hidden = false;
  const section = document.createElement("section");
  section.className = "source-group";
  section.setAttribute("aria-labelledby", `source-group-${key}`);

  const heading = document.createElement("div");
  heading.className = "source-group-heading";
  const title = document.createElement("h3");
  title.id = `source-group-${key}`;
  title.textContent = group.detailLabel;
  const summary = document.createElement("p");
  summary.textContent = `${entries.length} source${entries.length === 1 ? "" : "s"} in this category.`;
  heading.append(title, summary);

  const grid = document.createElement("div");
  grid.className = "source-card-grid";
  for (const { site, index } of entries) {
    appendSourceCard(grid, site, index);
  }

  section.append(heading, grid);
  detail.appendChild(section);
}


function selectSourceGroup(key, restoreFocus = false) {
  selectedSourceGroupKey = key;
  const select = $("sourceInfoSelect");
  if (select) select.value = "";
  renderSourceStatusCounts(sourceStatusCounts());
  renderSelectedSource();
  if (restoreFocus) {
    const activeButton = Array.from($("sourceStatusCounts")?.querySelectorAll("button[data-source-group]") || [])
      .find((button) => button.dataset.sourceGroup === key);
    activeButton?.focus();
  }
}

function renderSourceStatusCounts(counts) {
  const container = $("sourceStatusCounts");
  if (!container) return;

  container.innerHTML = "";
  for (const group of SOURCE_STATUS_GROUPS) {
    const valueCount = counts[group.key] || 0;
    const item = document.createElement("button");
    item.type = "button";
    item.className = `source-count${selectedSourceGroupKey === group.key ? " active" : ""}`;
    item.dataset.sourceGroup = group.key;
    item.setAttribute("aria-label", `${group.ariaLabel}: ${valueCount}. Show these sources.`);
    item.setAttribute("aria-pressed", String(selectedSourceGroupKey === group.key));
    item.addEventListener("click", () => selectSourceGroup(group.key, true));

    const value = document.createElement("span");
    value.className = "source-count-value";
    value.textContent = valueCount;

    const label = document.createElement("span");
    label.className = "source-count-label";
    label.textContent = group.label;

    item.append(value, label);
    container.appendChild(item);
  }
}

function updateSourceSummary() {
  const counts = sourceStatusCounts();
  $("totalSources").textContent = counts.enabled;
  $("sourceSummaryMeta").textContent = `${counts.total} configured total: ${counts.parserStart} parser starts, ${counts.backlog} backlog, ${counts.policyBlocked} policy/ref`;
  $("sourcesSummary").setAttribute(
    "aria-label",
    `${counts.enabled} connected or enabled sources; ${counts.total} total configured: ${counts.parserStart} disabled parser starts, ${counts.backlog} disabled backlog sources, ${counts.policyBlocked} policy-blocked or reference sources. Show source status counts and details.`
  );
  renderSourceStatusCounts(counts);
}

function sourceOptionLabel(site) {
  const stage = sourceStage(site);
  return `${site.name || "Unnamed source"} - ${stage.label}`;
}

function appendSourceCard(parent, site, index) {
  const stage = sourceStage(site);
  const card = document.createElement("article");
  card.className = `source-card ${stage.cardClass}`;
  if (Number.isInteger(index)) card.setAttribute("aria-labelledby", `source-info-title-${index}`);

  const title = document.createElement("a");
  if (Number.isInteger(index)) title.id = `source-info-title-${index}`;
  title.href = site.base_url || site.inventory_urls?.[0] || "#";
  title.target = "_blank";
  title.rel = "noopener noreferrer";
  title.textContent = site.name || "Unnamed source";

  const status = document.createElement("span");
  status.className = `source-status ${stage.statusClass}`;
  status.textContent = stage.label;

  const heading = document.createElement("div");
  heading.className = "source-card-heading";
  heading.append(title, status);

  const description = document.createElement("p");
  description.textContent = site.description || "No description provided.";

  const notes = document.createElement("p");
  notes.className = "source-notes";
  notes.textContent = site.notes || (siteIsEnabled(site) ? "Enabled source with a verified parser." : "Disabled source; parser verification is still required before enabling.");

  const meta = document.createElement("div");
  meta.className = "source-meta";
  const parser = document.createElement("span");
  parser.textContent = site.parser ? `Parser: ${site.parser}` : "Parser: not implemented";
  const urlCount = document.createElement("span");
  const inventoryCount = site.inventory_urls?.length || 0;
  urlCount.textContent = `${inventoryCount} inventory URL${inventoryCount === 1 ? "" : "s"}`;
  meta.append(parser, urlCount);

  const url = document.createElement("div");
  url.className = "source-url";
  url.textContent = site.base_url || "—";

  card.append(heading, description, notes, meta, url);
  parent.appendChild(card);
}

function renderSelectedSource() {
  const select = $("sourceInfoSelect");
  const detail = $("sourceInfoDetail");
  const index = Number.parseInt(select.value, 10);
  const site = allSites[index];

  detail.innerHTML = "";
  if (!site) {
    if (selectedSourceGroupKey) {
      renderSourceGroup(selectedSourceGroupKey);
      return;
    }
    detail.hidden = true;
    return;
  }

  selectedSourceGroupKey = "";
  renderSourceStatusCounts(sourceStatusCounts());
  detail.hidden = false;
  appendSourceCard(detail, site, index);
}

function renderSources() {
  const select = $("sourceInfoSelect");
  const previousValue = select.value;
  updateSourceSummary();

  select.innerHTML = "";
  select.disabled = allSites.length === 0;

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = allSites.length ? "Select a source..." : "No configured sources";
  select.appendChild(placeholder);

  if (!allSites.length) {
    renderSelectedSource();
    return;
  }

  const sortedSites = sortedSourceEntries();

  for (const { site, index } of sortedSites) {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = sourceOptionLabel(site);
    select.appendChild(option);
  }

  select.value = [...select.options].some((option) => option.value === previousValue) ? previousValue : "";
  renderSelectedSource();
}

function render() {
  currentType = $("typeFilter").value;
  if (!currentType) currentSubtype = "";
  const baseItems = visibleBaseListings();
  const chartScopeItems = filteredListings(baseItems);
  reconcilePriceDistributionFilter(chartScopeItems);
  const items = priceDistributionFilter
    ? chartScopeItems.filter((item) => matchesPriceDistributionFilter(item))
    : chartScopeItems;
  const tbody = $("results");
  const tpl = $("rowTemplate");

  tbody.innerHTML = "";
  updateSummary(items);
  renderPriceDistribution(chartScopeItems);
  renderPriceDistributionFilterControl(items.length);
  updateSortHeaders();
  renderChips(chipCountListings(baseItems));

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

    showImageAtIndex(thumb, noImage, item);

    title.textContent = item.title || "Untitled listing";
    title.href = item.url;
    row.querySelector(".classification").textContent = item.classification_text || "";
    row.querySelector(".type").textContent = categoryLabel(itemCategoryKey(item));
    row.querySelector(".subtype").textContent = subtypeDisplayLabel(item.subtype);
    const priceCell = row.querySelector(".price");
    const priceText = money(usdPriceValue(item), "USD");
    const originalPrice = originalPriceLabel(item);
    priceCell.textContent = priceText;
    if (originalPrice) {
      priceCell.title = originalPrice;
      priceCell.setAttribute("aria-label", `${priceText}; ${originalPrice}`);
    }
    row.querySelector(".weight").textContent = grams(item.weight_g);
    row.querySelector(".ppg").textContent = pricePerGDisplay(item);
    row.querySelector(".source").textContent = item.source || "—";
    row.querySelector(".confidence").textContent = item.confidence || "—";
    const availability = row.querySelector(".availability");
    availability.textContent = "";
    availability.classList.add(isUnavailable(item) ? "unavailable" : "available");
    const statusText = document.createElement("div");
    const verifiedText = document.createElement("div");
    const verifiedAt = item.last_verified_at || item.scraped_at;
    statusText.textContent = isUnavailable(item) ? "Unavailable" : "Available";
    verifiedText.className = "verified-at";
    verifiedText.textContent = verifiedDateLabel(verifiedAt);
    availability.title = verifiedAt ? `Last verified: ${new Date(verifiedAt).toLocaleString()}` : "Last verified timestamp unavailable";
    availability.append(statusText, verifiedText);
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
  setSourcesPanelOpen(false);
  fillFilters();
  renderSources();
  $("sourcesSummary").addEventListener("click", openSourcesPanel);
  $("sourceInfoSelect").addEventListener("change", renderSelectedSource);

  for (const id of ["search", "typeFilter", "sourceFilter"]) {
    $(id).addEventListener("input", () => {
      clearPriceDistributionFilter();
      if (id === "typeFilter") {
        currentType = $("typeFilter").value;
        currentSubtype = "";
        expandedType = currentType;
      }
      render();
    });
  }

  $("sortBy").addEventListener("input", () => {
    sortState = parseSort($("sortBy").value);
    render();
  });

  $("includeUnavailable").addEventListener("change", () => {
    clearPriceDistributionFilter();
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
