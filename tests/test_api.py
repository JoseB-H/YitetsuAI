import os
import unittest
import uuid

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from fastapi.testclient import TestClient

from main import app
from interpretation import interpret_prompt


class ConversationPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

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
            json={"email": email, "password": "test-password-123", "full_name": "Another User"},
        )
        self.assertEqual(duplicate.status_code, 409)

        login = self.client.post(
            "/auth/login",
            json={"email": email, "password": "test-password-123"},
        )
        self.assertEqual(login.status_code, 200, login.text)

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

    def test_interpretation_preserves_accents_and_corrects_unambiguous_english_typos(self):
        prompt = "How can I definately recieve help?"
        interpretation = interpret_prompt(prompt)
        self.assertEqual(interpretation.interpreted, "How can I definitely receive help?")
        self.assertEqual(
            interpretation.corrections,
            (("definately", "definitely"), ("recieve", "receive")),
        )

    def test_ambiguous_unknown_words_are_left_unchanged(self):
        prompt = "xyzzy blorpt"
        interpretation = interpret_prompt(prompt)
        self.assertEqual(interpretation.interpreted, prompt)


if __name__ == "__main__":
    unittest.main()
