import sqlite3
from pathlib import Path

from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    # Создаём базу и добавляем только отсутствующие учебные данные.
    # Перезапуск сервера не удаляет и не перезаписывает заметки.
    Path(current_app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    db = get_db()
    schema_path = Path(current_app.root_path) / "schema.sql"
    db.executescript(schema_path.read_text(encoding="utf-8"))

    for user_id, username, password in [(1, "alice", "alice123"), (2, "bob", "bob123")]:
        if db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone() is None:
            db.execute(
                "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
                (user_id, username, generate_password_hash(password)),
            )

    db.executemany(
        "INSERT OR IGNORE INTO notes (id, owner_id, title, content) VALUES (?, ?, ?, ?)",
        [
            (1, 1, "План Алисы", "Подготовить учебный проект и проверить вход в приложение."),
            (2, 1, "Личная заметка Алисы", "Учебный код Алисы: ALICE-DEMO-42. Эта заметка принадлежит alice."),
            (3, 2, "План Боба", "Повторить HTTP-запросы и выполнить упражнения по Python."),
            (4, 2, "Личная заметка Боба", "Учебный код Боба: BOB-DEMO-73. Эта заметка принадлежит bob."),
        ],
    )
    db.commit()
