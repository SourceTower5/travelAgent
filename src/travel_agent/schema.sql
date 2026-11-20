CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    departure_date TEXT NOT NULL,
    passengers INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fares (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    departure_date TEXT NOT NULL,
    cabin TEXT NOT NULL,
    price REAL NOT NULL,
    currency TEXT NOT NULL,
    available_seats INTEGER,
    observed_at TEXT NOT NULL,
    booking_url TEXT,
    return_date TEXT,
    trip_type TEXT NOT NULL DEFAULT 'one_way',
    price_kind TEXT NOT NULL DEFAULT 'displayed',
    source_freshness TEXT,
    FOREIGN KEY (search_id) REFERENCES searches (id)
);
