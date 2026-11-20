const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];
const AIRPORTS = {
  SFO: "San Francisco",
  SJC: "San Jose",
  NRT: "Tokyo Narita",
  HND: "Tokyo Haneda",
  OSA: "Osaka",
  ITM: "Osaka Itami",
  KIX: "Osaka Kansai",
  CTS: "Sapporo",
  FUK: "Fukuoka",
  HIJ: "Hiroshima",
};
const PROVIDERS = {
  "ana-google": "ANA (Google Flights)",
  jal: "JAL (Official)",
  "jal-google": "JAL (Google Flights)",
  zipair: "ZIPAIR",
};

let payload = null;
let activeProvider = "";
let activeOrigin = "";
let activeDestination = "";
let activeCabin = "All";

const providerSelect = document.querySelector("#provider-select");
const originSelect = document.querySelector("#origin-select");
const destinationSelect = document.querySelector("#destination-select");
const routeTitle = document.querySelector("#route-title");
const routeSubtitle = document.querySelector("#route-subtitle");
const calendar = document.querySelector("#calendar");
const summary = document.querySelector("#summary");
const dataStatus = document.querySelector("#data-status");
const cabinTabs = document.querySelector("#cabin-tabs");

function money(value, currency) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(value);
}

function setSelectOptions(select, values, selectedValue, labelFor) {
  select.replaceChildren();
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = labelFor(value);
    option.selected = value === selectedValue;
    select.append(option);
  }
}

function syncRouteControls() {
  const providers = [...new Set(payload.routes.map((route) => route.provider))].sort();
  if (!providers.includes(activeProvider)) activeProvider = providers[0];
  setSelectOptions(
    providerSelect,
    providers,
    activeProvider,
    (provider) => PROVIDERS[provider] ?? provider.toUpperCase(),
  );

  const origins = [...new Set(
    payload.routes
      .filter((route) => route.provider === activeProvider)
      .map((route) => route.origin)
  )].sort();
  if (!origins.includes(activeOrigin)) activeOrigin = origins[0];
  setSelectOptions(
    originSelect,
    origins,
    activeOrigin,
    (origin) => `${AIRPORTS[origin] ?? origin} (${origin})`,
  );

  const destinations = [...new Set(
    payload.routes
      .filter((route) => route.provider === activeProvider && route.origin === activeOrigin)
      .map((route) => route.destination)
  )].sort();
  if (!destinations.includes(activeDestination)) activeDestination = destinations[0];
  setSelectOptions(
    destinationSelect,
    destinations,
    activeDestination,
    (destination) => `${AIRPORTS[destination] ?? destination} (${destination})`,
  );
}

function faresByDate(fares) {
  const result = new Map();
  for (const fare of fares) {
    const existing = result.get(fare.departure_date) ?? [];
    existing.push(fare);
    result.set(fare.departure_date, existing);
  }
  return result;
}

function dayCell(year, month, day, fareMap) {
  const date = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  const dateFares = fareMap.get(date) ?? [];
  const matchingFares = activeCabin === "All"
    ? dateFares
    : dateFares.filter((fare) => fare.cabin === activeCabin);
  const cheapestByCabin = new Map();
  for (const fare of matchingFares) {
    const current = cheapestByCabin.get(fare.cabin);
    if (!current || fare.price < current.price) cheapestByCabin.set(fare.cabin, fare);
  }
  const fares = [...cheapestByCabin.values()];

  const cell = document.createElement("div");
  cell.className = `day ${fares.length ? "available" : "unavailable"}`;
  const prices = fares.map((fare) => `
    <span class="price ${fare.cabin.toLowerCase().includes("full-flat") ? "full-flat" : ""}">
      ${activeCabin === "All" ? `<small>${fare.cabin}</small>` : ""}
      ${fare.price_kind === "from" ? "<small>FROM</small>" : ""}
      ${money(fare.price, fare.currency)}
    </span>
  `).join("");
  cell.innerHTML = `<strong>${day}</strong>${prices || "<span class=\"dash\">—</span>"}`;
  if (fares.length) {
    cell.title = fares.map((fare) => {
      const returnText = fare.return_date ? ` · returns ${fare.return_date}` : "";
      const freshness = fare.source_freshness ? ` · ${fare.source_freshness}` : "";
      const qualifier = fare.price_kind === "from" ? "From " : "";
      return `${fare.cabin}: ${qualifier}${money(fare.price, fare.currency)}${returnText}${freshness} · scraped ${new Date(fare.observed_at).toLocaleString()}`;
    }).join("\n");
  }
  return cell;
}

function renderCabinTabs(routeFares) {
  const cabins = [...new Set(routeFares.map((fare) => fare.cabin))].sort();
  if (activeCabin !== "All" && !cabins.includes(activeCabin)) activeCabin = "All";
  cabinTabs.replaceChildren();
  for (const cabin of [...cabins, "All"]) {
    const button = document.createElement("button");
    button.className = `cabin-tab ${activeCabin === cabin ? "active" : ""}`;
    button.dataset.cabin = cabin;
    button.type = "button";
    button.role = "tab";
    button.textContent = cabin === "All" ? "Compare" : cabin;
    button.addEventListener("click", () => {
      activeCabin = cabin;
      render();
    });
    cabinTabs.append(button);
  }
}

function render() {
  const route = payload.routes.find((candidate) =>
    candidate.provider === activeProvider
      && candidate.origin === activeOrigin
      && candidate.destination === activeDestination
  );
  if (!route) return;
  routeTitle.textContent = `${AIRPORTS[route.origin] ?? route.origin} to ${AIRPORTS[route.destination] ?? route.destination}`;

  const routeFares = payload.fares.filter((fare) =>
    fare.provider === route.provider
      && fare.origin === route.origin
      && fare.destination === route.destination
  );
  if (route.provider === "ana") {
    const latestObservation = Math.max(...routeFares.map((fare) => Date.parse(fare.observed_at)));
    const ageHours = Math.max(0, (Date.now() - latestObservation) / 3_600_000);
    const observationAge = ageHours > 24
      ? `STALE · scraped ${Math.floor(ageHours / 24)}d ago`
      : ageHours >= 1
        ? `scraped ${Math.floor(ageHours)}h ago`
        : "scraped recently";
    routeSubtitle.textContent =
      `ANA cached round-trip “fares from” · ${observationAge} · verify availability with ANA`;
  } else if (route.provider === "ana-live") {
    routeSubtitle.textContent =
      "Official ANA live one-way seven-day slider fares · 1 adult";
  } else if (route.provider === "jal") {
    routeSubtitle.textContent =
      "Official JAL live one-way adjacent-date calendar fares · 1 adult";
  } else if (route.provider === "ana-google") {
    routeSubtitle.textContent =
      "Google Flights · ANA-only one-way price graph · 1 adult · verify before booking";
  } else if (route.provider === "jal-google") {
    routeSubtitle.textContent =
      "Google Flights · JAL-only one-way price graph · 1 adult · verify before booking";
  } else {
    routeSubtitle.textContent = "Latest locally observed one-way fares · 1 adult";
  }
  renderCabinTabs(routeFares);
  const shownFares = activeCabin === "All"
    ? routeFares
    : routeFares.filter((fare) => fare.cabin === activeCabin);
  const fareMap = faresByDate(routeFares);

  calendar.replaceChildren();
  const dates = routeFares.map((fare) => new Date(`${fare.departure_date}T12:00:00`));
  const firstDate = dates.length ? new Date(Math.min(...dates)) : new Date();
  const lastDate = dates.length ? new Date(Math.max(...dates)) : new Date();
  const firstMonth = new Date(firstDate.getFullYear(), firstDate.getMonth(), 1);
  const lastMonth = new Date(lastDate.getFullYear(), lastDate.getMonth(), 1);

  for (
    let cursor = firstMonth;
    cursor <= lastMonth;
    cursor = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1)
  ) {
    const year = cursor.getFullYear();
    const month = cursor.getMonth();
    const panel = document.createElement("article");
    panel.className = "month";
    panel.innerHTML = `
      <header><span>${MONTHS[month]}</span><small>${year}</small></header>
      <div class="weekdays">${WEEKDAYS.map((day) => `<span>${day}</span>`).join("")}</div>
      <div class="days"></div>
    `;
    const days = panel.querySelector(".days");
    const offset = new Date(year, month, 1).getDay();
    for (let blank = 0; blank < offset; blank += 1) {
      const spacer = document.createElement("div");
      spacer.className = "day spacer";
      days.append(spacer);
    }
    const dayCount = new Date(year, month + 1, 0).getDate();
    for (let day = 1; day <= dayCount; day += 1) {
      days.append(dayCell(year, month, day, fareMap));
    }
    calendar.append(panel);
  }

  if (shownFares.length) {
    const cheapest = shownFares.reduce((best, fare) => fare.price < best.price ? fare : best);
    const prefix = cheapest.price_kind === "from" ? "From " : "";
    const returnText = cheapest.return_date ? ` → ${cheapest.return_date}` : "";
    summary.innerHTML = `<span>Lowest observed</span><strong>${prefix}${money(cheapest.price, cheapest.currency)}</strong><small>${cheapest.departure_date}${returnText}</small>`;
  } else {
    summary.innerHTML = "<span>No stored fares for this cabin</span>";
  }
}

async function initialize() {
  const response = await fetch("/api/fares");
  if (!response.ok) throw new Error(`Could not load fares (${response.status})`);
  payload = await response.json();
  if (!payload.routes.length) throw new Error("The database has no supported fare data.");

  const firstRoute = payload.routes[0];
  activeProvider = firstRoute.provider;
  activeOrigin = firstRoute.origin;
  activeDestination = firstRoute.destination;
  syncRouteControls();
  providerSelect.addEventListener("change", () => {
    activeProvider = providerSelect.value;
    activeOrigin = "";
    activeDestination = "";
    activeCabin = "All";
    syncRouteControls();
    render();
  });
  originSelect.addEventListener("change", () => {
    activeOrigin = originSelect.value;
    activeDestination = "";
    activeCabin = "All";
    syncRouteControls();
    render();
  });
  destinationSelect.addEventListener("change", () => {
    activeDestination = destinationSelect.value;
    activeCabin = "All";
    render();
  });

  dataStatus.textContent = `${payload.fareCount} latest fare observations · ${payload.routes.length} provider routes`;
  render();
}

initialize().catch((error) => {
  routeTitle.textContent = "Could not load fare data";
  calendar.innerHTML = `<div class="error">${error.message}</div>`;
  dataStatus.textContent = "Database unavailable";
});
