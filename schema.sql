CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES users (id),
    title TEXT NOT NULL,
    content TEXT NOT NULL
);
