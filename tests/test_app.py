import tempfile
import unittest
from pathlib import Path

from app import app
from db import get_db, init_db


class NotesAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.original_database = app.config["DATABASE"]
        app.config.update(
            TESTING=True,
            DATABASE=str(Path(self.temp_directory.name) / "test.sqlite3"),
        )
        with app.app_context():
            init_db()
        self.client = app.test_client()

    def tearDown(self):
        app.config["DATABASE"] = self.original_database
        self.temp_directory.cleanup()

    def post_form(self, path, data=None):
        self.client.get("/")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        return self.client.post(path, data={**(data or {}), "csrf_token": token})

    def login(self, username="alice", password="alice123"):
        response = self.post_form("/login", {"username": username, "password": password})
        self.assertEqual(response.status_code, 302)

    def test_home_and_original_greeting(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn('<form action="/hello" method="get">', home.get_data(as_text=True))
        greeting = self.client.get("/hello", query_string={"name": "<b>Саша</b>"})
        self.assertIn("Привет, &lt;b&gt;Саша&lt;/b&gt;!", greeting.get_data(as_text=True))

    def test_anonymous_user_is_redirected_to_login(self):
        for path in ["/notes", "/notes/1", "/notes/4"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.headers["Location"].endswith("/login"))

    def test_wrong_password_does_not_start_authenticated_session(self):
        response = self.post_form("/login", {"username": "alice", "password": "wrong"})
        self.assertEqual(response.status_code, 401)
        self.assertIn("Неверный логин или пароль.", response.get_data(as_text=True))
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    def test_alice_ordinary_list_contains_only_her_notes(self):
        self.login()
        notes = self.client.get("/notes").get_data(as_text=True)
        self.assertIn("План Алисы", notes)
        self.assertNotIn("План Боба", notes)
        self.assertIn("ALICE-DEMO-42", self.client.get("/notes/2").get_data(as_text=True))
        self.assertEqual(self.client.get("/notes/999").status_code, 404)

    def test_bob_ordinary_list_contains_only_his_notes(self):
        self.login("bob", "bob123")
        notes = self.client.get("/notes").get_data(as_text=True)
        self.assertIn("План Боба", notes)
        self.assertNotIn("План Алисы", notes)
        self.assertIn("BOB-DEMO-73", self.client.get("/notes/4").get_data(as_text=True))

    def test_intentional_idor_allows_alice_to_read_bob_note(self):
        self.login()
        response = self.client.get("/notes/4")
        self.assertEqual(response.status_code, 200)
        self.assertIn("BOB-DEMO-73", response.get_data(as_text=True))
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_id"], 1)

    def test_intentional_idor_allows_bob_to_read_alice_note(self):
        self.login("bob", "bob123")
        response = self.client.get("/notes/2")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ALICE-DEMO-42", response.get_data(as_text=True))
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_id"], 2)

    def test_ordinary_search_matches_content(self):
        self.login()
        match = self.client.get("/notes", query_string={"q": "ALICE-DEMO-42"})
        self.assertIn("Личная заметка Алисы", match.get_data(as_text=True))
        self.assertNotIn("План Алисы", match.get_data(as_text=True))

    def test_intentional_sql_injection_exposes_other_users_titles(self):
        self.login()
        injection = self.client.get("/notes", query_string={"q": "') OR 1=1 -- "})
        self.assertEqual(injection.status_code, 200)
        html = injection.get_data(as_text=True)
        self.assertIn("План Алисы", html)
        self.assertIn("План Боба", html)
        self.assertIn("Личная заметка Боба", html)

    def test_malformed_search_returns_controlled_error(self):
        self.login()
        response = self.client.get("/notes", query_string={"q": "';"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Ошибка поискового SQL-запроса.", response.get_data(as_text=True))

    def test_post_requires_token_and_logout_ends_session(self):
        response = self.client.post("/login", data={"username": "alice", "password": "alice123"})
        self.assertEqual(response.status_code, 400)
        self.login()
        self.assertEqual(self.post_form("/logout").status_code, 302)
        self.assertEqual(self.client.get("/notes").status_code, 302)

    def test_initialization_preserves_existing_notes_and_templates_escape_content(self):
        with app.app_context():
            db = get_db()
            db.execute("UPDATE notes SET content = ? WHERE id = 1", ("<b>Изменённая заметка</b>",))
            db.commit()
            init_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM notes").fetchone()[0], 4)
            self.assertEqual(db.execute("SELECT content FROM notes WHERE id = 1").fetchone()[0], "<b>Изменённая заметка</b>")
        self.login()
        note = self.client.get("/notes/1").get_data(as_text=True)
        self.assertIn("&lt;b&gt;Изменённая заметка&lt;/b&gt;", note)
        self.assertNotIn("<b>Изменённая заметка</b>", note)


if __name__ == "__main__":
    unittest.main()
