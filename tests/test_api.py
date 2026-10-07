import os
import unittest
import uuid

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from fastapi.testclient import TestClient

from main import app
from interpretation import interpret_prompt
from llm import get_chat_engine, attachment_context


class FakeChatEngine:
    async def answer(self, question, history, items):
        context, sources = attachment_context(question, items)
        return {
            "response": "Test model: " + context,
            "sources": sources,
            "warnings": [],
            "model": "test",
            "vision_model": None,
        }


class ConversationPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_chat_engine] = lambda: FakeChatEngine()
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        app.dependency_overrides.clear()

    def register(self, email: str) -> tuple[str, str]:
        response = self.client.post(
            "/auth/register",
            json={
                "email": email,
                "password": "test-password-123",
                "full_name": "Test User",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()
        return data["token"], data["user_id"]

    def test_chat_is_saved_and_can_be_loaded_from_history(self):
        token, _ = self.register(f"{uuid.uuid4()}@example.test")
        headers = {"Authorization": f"Bearer {token}"}

        response = self.client.post(
            "/chat",
            headers=headers,
            json={"prompt": "How can our team improve onboarding?"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        conversation_id = response.json()["conversation_id"]
        self.assertIsNotNone(conversation_id)

        second_turn = self.client.post(
            "/chat",
            headers=headers,
            json={
                "prompt": "What should we measure during that pilot?",
                "conversation_id": conversation_id,
            },
        )
        self.assertEqual(second_turn.status_code, 200, second_turn.text)

        history = self.client.get("/conversations", headers=headers)
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(len(history.json()), 1)
        self.assertEqual(history.json()[0]["message_count"], 4)

        messages = self.client.get(
            f"/conversations/{conversation_id}/messages",
            headers=headers,
        )
        self.assertEqual(messages.status_code, 200, messages.text)
        self.assertEqual(
            [message["role"] for message in messages.json()],
            ["user", "assistant", "user", "assistant"],
        )

    def test_guest_chat_does_not_create_persisted_conversation(self):
        response = self.client.post(
            "/chat",
            json={"prompt": "How can we improve the review process?"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["conversation_id"])

    def test_user_cannot_read_another_users_conversation(self):
        owner_token, _ = self.register(f"{uuid.uuid4()}@example.test")
        other_token, _ = self.register(f"{uuid.uuid4()}@example.test")
        chat = self.client.post(
            "/chat",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"prompt": "How can we improve the review process?"},
        )
        conversation_id = chat.json()["conversation_id"]

        response = self.client.get(
            f"/conversations/{conversation_id}/messages",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(response.status_code, 404)

    def test_password_is_hashed_and_duplicate_email_is_rejected(self):
        email = f"{uuid.uuid4()}@example.test"
        self.register(email)
        duplicate = self.client.post(
            "/auth/register",
            json={
                "email": email,
                "password": "test-password-123",
                "full_name": "Another User",
            },
        )
        self.assertEqual(duplicate.status_code, 409)

        login = self.client.post(
            "/auth/login",
            json={"email": email, "password": "test-password-123"},
        )
        self.assertEqual(login.status_code, 200, login.text)

    def test_attachments_are_private_and_used_with_persisted_sources(self):
        token, _ = self.register(f"{uuid.uuid4()}@example.test")
        other, _ = self.register(f"{uuid.uuid4()}@example.test")
        headers = {"Authorization": f"Bearer {token}"}
        foreign = {"Authorization": f"Bearer {other}"}
        upload = self.client.post(
            "/attachments",
            headers=headers,
            files={
                "file": (
                    "ventas.csv",
                    b"product,revenue\nAurora,12\nBoreal,18\n",
                    "text/csv",
                )
            },
        )
        self.assertEqual(upload.status_code, 201, upload.text)
        item = upload.json()
        identifier = item["attachment_id"]
        conversation = item["conversation_id"]
        details = self.client.get(f"/attachments/{identifier}", headers=headers)
        self.assertEqual(
            details.json()["metadata"]["numeric_columns"]["revenue"]["sum"], "30"
        )
        for suffix in ("", "/download"):
            self.assertEqual(
                self.client.get(
                    f"/attachments/{identifier}{suffix}", headers=foreign
                ).status_code,
                404,
            )
        self.assertEqual(
            self.client.delete(
                f"/attachments/{identifier}", headers=foreign
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/attachments",
                headers=foreign,
                data={"conversation_id": conversation},
                files={"file": ("other.txt", b"private")},
            ).status_code,
            404,
        )
        second = self.client.post(
            "/attachments",
            headers=headers,
            data={"conversation_id": conversation},
            files={
                "file": ("objetivo.json", b'{"target_revenue":30}', "application/json")
            },
        )
        self.assertEqual(second.status_code, 201, second.text)
        second_id = second.json()["attachment_id"]
        answer = self.client.post(
            "/chat",
            headers=headers,
            json={
                "prompt": "Compara ingresos Aurora y Boreal",
                "conversation_id": conversation,
                "attachment_ids": [identifier, second_id],
            },
        )
        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertEqual(
            {source["filename"] for source in answer.json()["sources"]},
            {"ventas.csv", "objetivo.json"},
        )
        history = self.client.get(
            f"/conversations/{conversation}/messages", headers=headers
        ).json()
        self.assertEqual(history[-1]["sources"], answer.json()["sources"])
        excluded = self.client.post(
            "/chat",
            headers=headers,
            json={
                "prompt": "Pregunta sin archivos",
                "conversation_id": conversation,
                "attachment_ids": [],
            },
        )
        self.assertEqual(excluded.json()["sources"], [])
        self.assertEqual(
            self.client.get(
                f"/attachments/{identifier}/download", headers=headers
            ).content,
            b"product,revenue\nAurora,12\nBoreal,18\n",
        )
        self.assertEqual(
            self.client.delete(
                f"/attachments/{identifier}", headers=headers
            ).status_code,
            204,
        )
        self.assertEqual(
            self.client.get(f"/attachments/{identifier}", headers=headers).status_code,
            404,
        )

        self.assertEqual(
            self.client.delete(
                f"/attachments/{second_id}", headers=headers
            ).status_code,
            204,
        )

    def test_request_body_limit_rejects_large_payload_before_parsing(self):
        response = self.client.post(
            "/attachments",
            content=b"",
            headers={"Content-Length": str(27 * 1024 * 1024)},
        )
        self.assertEqual(response.status_code, 413)

    def test_invalid_uploads_and_guest_access_are_rejected(self):
        self.assertEqual(
            self.client.post(
                "/attachments", files={"file": ("data.txt", b"hello")}
            ).status_code,
            401,
        )
        token, _ = self.register(f"{uuid.uuid4()}@example.test")
        headers = {"Authorization": f"Bearer {token}"}
        for name, content, code in (
            ("run.exe", b"MZ", 415),
            ("empty.txt", b"", 422),
            ("fake.pdf", b"not a pdf", 422),
            ("bad.json", b"{", 422),
            (
                "bad.xml",
                b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>',
                422,
            ),
        ):
            response = self.client.post(
                "/attachments", headers=headers, files={"file": (name, content)}
            )
            self.assertEqual(response.status_code, code, response.text)
        response = self.client.post(
            "/attachments",
            headers=headers,
            files={"file": ("../secret.txt", b"visible safe data")},
        )
        self.assertEqual(response.json()["filename"], "secret.txt")
        self.client.delete(
            "/attachments/" + response.json()["attachment_id"], headers=headers
        )

    def test_missing_model_is_reported_without_fake_reply_or_saved_messages(self):
        from llm import ModelUnavailable

        class MissingModel:
            async def answer(self, *args):
                raise ModelUnavailable("Missing model")

        app.dependency_overrides[get_chat_engine] = lambda: MissingModel()
        try:
            token, _ = self.register(f"{uuid.uuid4()}@example.test")
            headers = {"Authorization": f"Bearer {token}"}
            response = self.client.post(
                "/chat", headers=headers, json={"prompt": "Test provider failure"}
            )
            self.assertEqual(response.status_code, 503)
            self.assertEqual(
                self.client.get("/conversations", headers=headers).json(), []
            )
        finally:
            app.dependency_overrides[get_chat_engine] = lambda: FakeChatEngine()

    def test_logout_revokes_the_persisted_session(self):
        token, _ = self.register(f"{uuid.uuid4()}@example.test")
        headers = {"Authorization": f"Bearer {token}"}

        logout = self.client.post("/auth/logout", headers=headers)
        self.assertEqual(logout.status_code, 200, logout.text)

        current_user = self.client.get("/users/me", headers=headers)
        self.assertEqual(current_user.status_code, 401)

    def test_chat_corrects_common_typos_and_keeps_the_original_message(self):
        token, _ = self.register(f"{uuid.uuid4()}@example.test")
        response = self.client.post(
            "/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "qiero aser una aplicasion"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["interpreted_prompt"], "quiero hacer una aplicación")
        self.assertEqual(
            data["corrections"],
            [
                {"original": "qiero", "corrected": "quiero"},
                {"original": "aser", "corrected": "hacer"},
                {"original": "aplicasion", "corrected": "aplicación"},
            ],
        )
        self.assertEqual(data["messages"][0]["content"], "qiero aser una aplicasion")

        saved_messages = self.client.get(
            f"/conversations/{data['conversation_id']}/messages",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        self.assertEqual(saved_messages[0]["content"], "qiero aser una aplicasion")

    def test_interpretation_preserves_punctuation_and_known_words(self):
        prompt = "Como podemos mejorar YitetsuAI?"
        interpretation = interpret_prompt(prompt)
        self.assertEqual(interpretation.interpreted, prompt)
        self.assertFalse(interpretation.was_corrected)

    def test_interpretation_preserves_accents_and_corrects_unambiguous_english_typos(
        self,
    ):
        prompt = "How can I definately recieve help?"
        interpretation = interpret_prompt(prompt)
        self.assertEqual(
            interpretation.interpreted, "How can I definitely receive help?"
        )
        self.assertEqual(
            interpretation.corrections,
            (("definately", "definitely"), ("recieve", "receive")),
        )

    def test_ambiguous_unknown_words_are_left_unchanged(self):
        prompt = "xyzzy blorpt"
        interpretation = interpret_prompt(prompt)
        self.assertEqual(interpretation.interpreted, prompt)

    def test_greeting_and_typo_in_name_question_get_a_relevant_answer(self):
        token, _ = self.register(f"{uuid.uuid4()}@example.test")
        response = self.client.post(
            "/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "hola como te llams "},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["interpreted_prompt"], "hola como te llamas ")
        self.assertIn("Soy YitetsuAI", data["response"])
        self.assertIn("Puedes llamarme Yitetsu", data["response"])
        self.assertNotIn("small pilot", data["response"])
        self.assertEqual(
            data["corrections"],
            [{"original": "llams", "corrected": "llamas"}],
        )

    def test_plain_greeting_gets_a_greeting_not_a_generic_project_template(self):
        response = self.client.post("/chat", json={"prompt": "hola"})
        self.assertEqual(response.status_code, 200, response.text)
        answer = response.json()["response"]
        self.assertIn("¡Hola!", answer)
        self.assertNotIn("small pilot", answer)


if __name__ == "__main__":
    unittest.main()
