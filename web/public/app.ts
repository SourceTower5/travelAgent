const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];
const AIRPORTS = {
  SFO: "San Francisco",
  SJC: "San Jose",
  NRT: "Tokyo Narita",
};

let payload = null;
let activeRoute = "";
let activeCabin = "Standard";

const routeSelect = document.querySelector("#route-select");
const routeTitle = document.querySelector("#route-title");
const calendar = document.querySelector("#calendar");
const summary = document.querySelector("#summary");
const dataStatus = document.querySelector("#data-status");

function money(value, currency) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(value);
}

function routeLabel(route) {
  const [origin, destination] = route.split("-");
  return `${AIRPORTS[origin] ?? origin} → ${AIRPORTS[destination] ?? destination}`;
}

function latestByDate(fares) {
  const result = new Map();
  for (const fare of fares) {
    const key = `${fare.departure_date}:${fare.cabin}`;
    result.set(key, fare);
  }
  return result;
}

function dayCell(year, month, day, fareMap) {
  const date = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  const standard = fareMap.get(`${date}:Standard`);
  const fullFlat = fareMap.get(`${date}:ZIP Full-Flat`);
  const fares = activeCabin === "All"
    ? [standard, fullFlat].filter(Boolean)
    : [fareMap.get(`${date}:${activeCabin}`)].filter(Boolean);

  const cell = document.createElement("div");
  cell.className = `day ${fares.length ? "available" : "unavailable"}`;
  const prices = fares.map((fare) => `
    <span class="price ${fare.cabin === "ZIP Full-Flat" ? "full-flat" : ""}">
      ${activeCabin === "All" ? `<small>${fare.cabin === "Standard" ? "STD" : "FULL"}</small>` : ""}
      ${money(fare.price, fare.currency)}
    </span>
  `).join("");
  cell.innerHTML = `<strong>${day}</strong>${prices || "<span class=\"dash\">—</span>"}`;
  if (fares.length) {
    cell.title = fares.map((fare) =>
      `${fare.cabin}: ${money(fare.price, fare.currency)} · observed ${new Date(fare.observed_at).toLocaleString()}`
    ).join("\n");
  }
  return cell;
}

function render() {
  const [origin, destination] = activeRoute.split("-");
  routeTitle.textContent = `${AIRPORTS[origin] ?? origin} to ${AIRPORTS[destination] ?? destination}`;

  const routeFares = payload.fares.filter((fare) =>
    `${fare.origin}-${fare.destination}` === activeRoute
  );
  const shownFares = activeCabin === "All"
    ? routeFares
    : routeFares.filter((fare) => fare.cabin === activeCabin);
  const fareMap = latestByDate(routeFares);

  calendar.replaceChildren();
  const dates = routeFares.map((fare) => new Date(`${fare.departure_date}T12:00:00`));
  const firstDate = dates.length ? new Date(Math.min(...dates)) : new Date();
  const lastDate = dates.length ? new Date(Math.max(...dates)) : new Date();
  const startMonth = firstDate.getMonth();
  const endMonth = Math.max(lastDate.getMonth(), 11);
  const year = firstDate.getFullYear();

  for (let month = startMonth; month <= endMonth; month += 1) {
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
    summary.innerHTML = `<span>Lowest observed</span><strong>${money(cheapest.price, cheapest.currency)}</strong><small>${cheapest.departure_date}</small>`;
  } else {
    summary.innerHTML = "<span>No stored fares for this cabin</span>";
  }
}

async function initialize() {
  const response = await fetch("/api/fares");
  if (!response.ok) throw new Error(`Could not load fares (${response.status})`);
  payload = await response.json();
  if (!payload.routes.length) throw new Error("The database has no ZIPAIR fares.");

  activeRoute = payload.routes[0];
  routeSelect.innerHTML = payload.routes
    .map((route) => `<option value="${route}">${routeLabel(route)} (${route})</option>`)
    .join("");
  routeSelect.value = activeRoute;
  routeSelect.addEventListener("change", () => {
    activeRoute = routeSelect.value;
    render();
  });
  document.querySelectorAll(".cabin-tab").forEach((button) => {
    button.addEventListener("click", () => {
      activeCabin = button.dataset.cabin;
      document.querySelectorAll(".cabin-tab").forEach((tab) =>
        tab.classList.toggle("active", tab === button)
      );
      render();
    });
  });

  dataStatus.textContent = `${payload.fareCount} latest fare observations · ${payload.routes.length} routes`;
  render();
}

initialize().catch((error) => {
  routeTitle.textContent = "Could not load fare data";
  calendar.innerHTML = `<div class="error">${error.message}</div>`;
  dataStatus.textContent = "Database unavailable";
});
