import os
import unittest

os.environ["ADMIN_EMAILS"] = "security@test.srmu.ac.in"
os.environ["SECRET_KEY"] = "test-only-signing-key-with-at-least-32-bytes"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_db


class CoreFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)

        def override_get_db():
            from sqlalchemy.orm import Session

            with Session(cls.engine) as db:
                yield db

        main.app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        main.app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.owner_token = self.register("owner@test.srmu.ac.in")["access_token"]
        self.claimant_token = self.register("claimant@test.srmu.ac.in")["access_token"]
        self.admin_token = self.register("security@test.srmu.ac.in")["access_token"]

    def register(self, email):
        response = self.client.post(
            "/auth/register",
            json={"name": "Test User", "email": email, "password": "test-pass-123"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def headers(self, token):
        return {"Authorization": f"Bearer {token}"}

    def create_found_report(self):
        response = self.client.post(
            "/items",
            headers=self.headers(self.owner_token),
            data={
                "type": "found",
                "title": "Blue calculator",
                "category": "gadgets",
                "location": "Library",
                "event_time": "2026-11-06T10:00:00",
                "secret_identifier": "Small star sticker on the back",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_claim_review_resolves_item_and_keeps_secret_private(self):
        report = self.create_found_report()

        public_report = self.client.get(f"/items/{report['id']}")
        owner_report = self.client.get(
            f"/items/{report['id']}", headers=self.headers(self.owner_token)
        )
        self.assertIsNone(public_report.json()["secret_identifier"])
        self.assertEqual(
            owner_report.json()["secret_identifier"],
            "Small star sticker on the back",
        )

        claim_response = self.client.post(
            f"/items/{report['id']}/claim",
            headers=self.headers(self.claimant_token),
            json={"proof_answer": "There is a small star sticker on the back"},
        )
        self.assertEqual(claim_response.status_code, 201, claim_response.text)

        admin_claims = self.client.get(
            "/admin/claims", headers=self.headers(self.admin_token)
        )
        self.assertEqual(admin_claims.status_code, 200, admin_claims.text)
        self.assertEqual(
            admin_claims.json()[0]["item_secret_identifier"],
            "Small star sticker on the back",
        )

        review = self.client.post(
            f"/admin/claims/{claim_response.json()['id']}/review",
            headers=self.headers(self.admin_token),
            json={"approve": True, "note": "Verified at security desk"},
        )
        self.assertEqual(review.status_code, 200, review.text)
        self.assertEqual(review.json()["status"], "approved")

        resolved_report = self.client.get(f"/items/{report['id']}")
        self.assertEqual(resolved_report.json()["status"], "claimed")

        my_claims = self.client.get(
            "/claims/mine", headers=self.headers(self.claimant_token)
        )
        self.assertEqual(my_claims.json()[0]["status"], "approved")

    def test_non_admin_cannot_review_claims(self):
        response = self.client.get(
            "/admin/claims", headers=self.headers(self.owner_token)
        )
        self.assertEqual(response.status_code, 403)

    def test_user_cannot_delete_another_users_report(self):
        report = self.create_found_report()
        response = self.client.delete(
            f"/items/{report['id']}", headers=self.headers(self.claimant_token)
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_can_get_matches_and_response_has_image_similarity_field(self):
        found = self.create_found_report()
        lost = self.client.post(
            "/items",
            headers=self.headers(self.claimant_token),
            data={
                "type": "lost",
                "title": "Blue calculator",
                "category": "gadgets",
                "location": "Library",
                "event_time": "2026-11-06T10:00:00",
            },
        )
        self.assertEqual(lost.status_code, 201, lost.text)

        matches = self.client.get(
            f"/items/{found['id']}/matches",
            headers=self.headers(self.owner_token),
        )
        self.assertEqual(matches.status_code, 200, matches.text)
        self.assertEqual(matches.json()[0]["item"]["id"], lost.json()["id"])
        self.assertIsNone(matches.json()[0]["image_similarity_percent"])

        forbidden = self.client.get(
            f"/items/{found['id']}/matches",
            headers=self.headers(self.claimant_token),
        )
        self.assertEqual(forbidden.status_code, 403)


if __name__ == "__main__":
    unittest.main()
