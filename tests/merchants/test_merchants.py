from tests.base import BaseAPITest

class TestMerchants(BaseAPITest):

    def test_user_can_create_multiple_tenants(self):
        user, pwd = self.create_user()
        self.authenticate(user.email, pwd)

        tenant1 = self.create_merchant(name="Store A")
        print(tenant1)
        tenant2 = self.create_merchant(name="Store B")

        self.assertNotEqual(tenant1, tenant2)

    def test_user_a_cannot_see_user_b_merchant(self):
        # -------------------------------
        # User A creates a merchant
        # -------------------------------
        user_a, pass_a = self.create_user("a@test.com")
        self.authenticate("a@test.com", pass_a)
        merchant_a_id = self.create_merchant("Merchant A")

        # List as User A (should see only their merchant)
        res_a_list = self.client.get("/api/v1/merchants/")
        self.assertEqual(len(res_a_list.json()), 1)
        self.assertEqual(res_a_list.json()[0]["id"], merchant_a_id)

        # -------------------------------
        # User B creates a merchant
        # -------------------------------
        self.client.credentials()  # remove auth token
        user_b, pass_b = self.create_user("b@test.com")
        self.authenticate("b@test.com", pass_b)
        merchant_b_id = self.create_merchant("Merchant B")
        print(f"Merchant B ID: {merchant_b_id}")

        # List as User B (should see only merchant B)
        res_b_list = self.client.get("/api/v1/merchants/")
        self.assertEqual(len(res_b_list.json()), 1)
        self.assertEqual(res_b_list.json()[0]["id"], merchant_b_id)

        # -------------------------------
        # User A tries to view B's merchant detail
        # -------------------------------
        self.client.credentials()  # remove token
        self.authenticate("a@test.com", pass_a)

        res_forbidden = self.client.get(f"/api/v1/merchants/{merchant_b_id}/")
        print(f"Response status code: {res_forbidden.status_code}")
        self.assertEqual(res_forbidden.status_code, 404)  # Permission denied


    def test_user_a_cannot_delete_user_b_merchant(self):
        # -------------------------------
        # User A creates a merchant
        # -------------------------------
        user_a, pass_a = self.create_user("a@test.com")
        self.authenticate("a@test.com", pass_a)
        merchant_a_id = self.create_merchant("Merchant A")

        # -------------------------------
        # User B creates another merchant
        # -------------------------------
        self.client.credentials()
        user_b, pass_b = self.create_user("b@test.com")
        self.authenticate("b@test.com", pass_b)
        merchant_b_id = self.create_merchant("Merchant B")

        # -------------------------------
        # User A tries to delete merchant B
        # -------------------------------
        self.client.credentials()
        self.authenticate("a@test.com", pass_a)

        res = self.client.delete(f"/api/v1/merchants/{merchant_b_id}/")
        self.assertEqual(res.status_code, 404)  # forbidden
        self.assertTrue("matches the given query" in res.json()["detail"].lower())

    def test_unauthenticated_user_cannot_access_merchants(self):
        # -------------------------------
        # User creates a merchant
        # -------------------------------
        user, password = self.create_user("user@test.com")
        self.authenticate("user@test.com", password)
        merchant_id = self.create_merchant("Merchant 1")

        # -------------------------------
        # Remove authentication
        # -------------------------------
        self.client.credentials()  # Removes Bearer token

        # Access list
        res_list = self.client.get("/api/v1/merchants/")
        self.assertEqual(res_list.status_code, 401)  # unauthorized

        # Access detail
        res_detail = self.client.get(f"/api/v1/merchants/{merchant_id}/")
        self.assertEqual(res_detail.status_code, 401)

        # Try create merchant
        res_create = self.client.post("/api/v1/merchants/", {"name": "Unauthorized Merchant"})
        self.assertEqual(res_create.status_code, 401)
