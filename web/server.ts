import { createReadStream, existsSync } from "node:fs";
import { createServer, type ServerResponse } from "node:http";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

const host = process.env.TRAVEL_AGENT_WEB_HOST ?? "127.0.0.1";
const port = Number(process.env.TRAVEL_AGENT_WEB_PORT ?? "4173");
const databasePath = resolve(process.env.TRAVEL_AGENT_DB ?? "travel_agent.sqlite");
const publicDirectory = fileURLToPath(new URL("./public/", import.meta.url));

if (!existsSync(databasePath)) {
  throw new Error(
    `TravelAgent database not found at ${databasePath}. Run a scan first or set TRAVEL_AGENT_DB.`,
  );
}

const database = new DatabaseSync(databasePath, { readOnly: true });

type FareRow = {
  provider: string;
  origin: string;
  destination: string;
  departure_date: string;
  return_date: string | null;
  trip_type: string;
  cabin: string;
  price: number;
  price_kind: string;
  currency: string;
  available_seats: number | null;
  observed_at: string;
  source_freshness: string | null;
};

const latestFares = database.prepare(`
  WITH ranked_fares AS (
    SELECT
      fares.*,
      ROW_NUMBER() OVER (
        PARTITION BY provider, origin, destination, departure_date, cabin
        ORDER BY observed_at DESC, id DESC
      ) AS date_rank
    FROM fares
    WHERE provider IN ('ana-google', 'jal', 'jal-google', 'zipair')
      AND (
        destination IN ('HND', 'NRT')
        OR (origin = 'SFO' AND destination IN ('ITM', 'KIX', 'OSA'))
        OR (
          provider = 'zipair'
          AND origin = 'NRT'
          AND destination IN ('SFO', 'SJC')
        )
        OR (
          provider IN ('ana-google', 'jal', 'jal-google')
          AND origin IN ('HND', 'NRT', 'KIX')
          AND destination IN ('SFO', 'SJC')
        )
      )
  )
  SELECT
    provider,
    origin,
    destination,
    departure_date,
    return_date,
    trip_type,
    cabin,
    price,
    price_kind,
    currency,
    available_seats,
    observed_at,
    source_freshness
  FROM ranked_fares
  WHERE date_rank = 1
  ORDER BY provider, origin, destination, departure_date, cabin
`);

function sendJson(response: ServerResponse, value: unknown): void {
  response.writeHead(200, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  response.end(JSON.stringify(value));
}

function serveStatic(pathname: string, response: ServerResponse): void {
  const relativePath = pathname === "/" ? "index.html" : pathname.slice(1);
  const filePath = resolve(join(publicDirectory, relativePath));
  if (!filePath.startsWith(resolve(publicDirectory)) || !existsSync(filePath)) {
    response.writeHead(404);
    response.end("Not found");
    return;
  }
  const contentTypes: Record<string, string> = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".ts": "text/javascript; charset=utf-8",
  };
  response.writeHead(200, {
    "Content-Type": contentTypes[extname(filePath)] ?? "application/octet-stream",
    "Cache-Control": "no-store",
  });
  createReadStream(filePath).pipe(response);
}

const server = createServer((request, response) => {
  const url = new URL(request.url ?? "/", `http://${request.headers.host ?? host}`);
  if (url.pathname === "/api/fares") {
    const fares = latestFares.all() as FareRow[];
    const routeMap = new Map(
      fares.map((fare) => {
        const id = `${fare.provider}:${fare.origin}-${fare.destination}`;
        return [
          id,
          {
            id,
            provider: fare.provider,
            origin: fare.origin,
            destination: fare.destination,
          },
        ];
      }),
    );
    for (const route of [
      { provider: "zipair", origin: "NRT", destination: "SFO" },
      { provider: "zipair", origin: "NRT", destination: "SJC" },
    ]) {
      const id = `${route.provider}:${route.origin}-${route.destination}`;
      if (!routeMap.has(id)) routeMap.set(id, { id, ...route });
    }
    sendJson(response, {
      database: databasePath,
      routes: [...routeMap.values()],
      fareCount: fares.length,
      fares,
    });
    return;
  }
  serveStatic(url.pathname, response);
});

server.listen(port, host, () => {
  console.log(`TravelAgent dashboard: http://${host}:${port}`);
  console.log(`Reading: ${databasePath}`);
});
