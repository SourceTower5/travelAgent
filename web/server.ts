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
  origin: string;
  destination: string;
  departure_date: string;
  cabin: string;
  price: number;
  currency: string;
  available_seats: number | null;
  observed_at: string;
};

const latestFares = database.prepare(`
  WITH batches AS (
    SELECT
      origin,
      destination,
      observed_at,
      COUNT(*) AS fare_count
    FROM fares
    WHERE provider = 'zipair'
      AND cabin IN ('Standard', 'ZIP Full-Flat')
    GROUP BY origin, destination, observed_at
  ),
  ranked_batches AS (
    SELECT
      origin,
      destination,
      observed_at,
      ROW_NUMBER() OVER (
        PARTITION BY origin, destination
        ORDER BY CASE WHEN fare_count >= 3 THEN 1 ELSE 0 END DESC, observed_at DESC
      ) AS rank
    FROM batches
  )
  SELECT
    fares.origin,
    fares.destination,
    fares.departure_date,
    fares.cabin,
    fares.price,
    fares.currency,
    fares.available_seats,
    fares.observed_at
  FROM fares
  JOIN ranked_batches
    ON ranked_batches.origin = fares.origin
   AND ranked_batches.destination = fares.destination
   AND ranked_batches.observed_at = fares.observed_at
  WHERE ranked_batches.rank = 1
  ORDER BY fares.origin, fares.destination, fares.departure_date, fares.cabin
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
    const routes = [...new Set(fares.map((fare) => `${fare.origin}-${fare.destination}`))];
    sendJson(response, {
      database: databasePath,
      routes,
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
