import secrets
import sqlite3

from flask import Flask, abort, g, redirect, render_template, request, session, url_for
from markupsafe import escape
from werkzeug.security import check_password_hash

from db import close_db, get_db, init_db

app = Flask(__name__)
app.config.update(
    DATABASE=f"{app.instance_path}/notes.sqlite3",
    SECRET_KEY=secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
app.teardown_appcontext(close_db)

with app.app_context():
    init_db()


@app.before_request
def load_user():
    # Токен связывает POST-формы с текущей сессией браузера.
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    if request.method == "POST":
        if request.form.get("csrf_token") != session["csrf_token"]:
            abort(400)

    g.user = None
    user_id = session.get("user_id")
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT id, username FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if g.user is None:
            session.clear()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/hello")
def hello():
    name = request.args.get("name", "гость")
    return (
        f"<h1>Привет, {escape(name)}!</h1>"
        '<p><a href="/">Вернуться к форме</a></p>'
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("notes"))

    error = None
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            error = "Неверный логин или пароль."
        else:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("notes"))

    return render_template("login.html", error=error, username=username), 401 if error else 200


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/notes")
def notes():
    if g.user is None:
        return redirect(url_for("login"))

    query = request.args.get("q", "")
    # Намеренная учебная SQL-инъекция: ввод пользователя становится частью SQL.
    sql = (
        f"SELECT id, title FROM notes WHERE owner_id = {g.user['id']} "
        f"AND (title LIKE '%{query}%' OR content LIKE '%{query}%') ORDER BY id"
    )
    try:
        user_notes = get_db().execute(sql).fetchall()
    except sqlite3.Error:
        return render_template(
            "notes.html", notes=[], query=query,
            error="Ошибка поискового SQL-запроса. Проверь введённую строку.",
        ), 400

    return render_template("notes.html", notes=user_notes, query=query, error=None)


@app.route("/notes/<int:note_id>")
def note_detail(note_id):
    if g.user is None:
        return redirect(url_for("login"))

    note = get_db().execute(
        "SELECT * FROM notes WHERE id = ?", (note_id,)
    ).fetchone()
    if note is None:
        abort(404)

    # Намеренная учебная IDOR: вход проверен, но владелец заметки не проверяется.
    return render_template("note.html", note=note)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
