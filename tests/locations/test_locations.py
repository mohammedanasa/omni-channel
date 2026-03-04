from tests.base import BaseAPITest   # adjust import path

class TestLocations(BaseAPITest):

    def test_user_a_cannot_see_user_b_locations(self):
        # User A setup
        user_a, pass_a = self.create_user("a@test.com")
        self.authenticate("a@test.com", pass_a)
        merchant_a = self.create_merchant("Merchant A")

        # Create A's location
        res_loc_a = self.client.post("/api/v1/locations/", 
                                     {"name": "A-Location"},
                                     **self.merchant_headers(merchant_a))
        loc_a_id = res_loc_a.json()["id"]

        # User B setup
        self.client.credentials()
        user_b, pass_b = self.create_user("b@test.com")
        self.authenticate("b@test.com", pass_b)
        merchant_b = self.create_merchant("Merchant B")

        # Create B's location
        res_loc_b = self.client.post("/api/v1/locations/",
                                     {"name": "B-Location"},
                                     **self.merchant_headers(merchant_b))
        loc_b_id = res_loc_b.json()["id"]

        # User A should NOT see B's locations
        self.client.credentials()
        self.authenticate("a@test.com", pass_a)
        res = self.client.get("/api/v1/locations/", **self.merchant_headers(merchant_b))
        self.assertEqual(res.status_code, 403)


    def test_user_a_cannot_delete_user_b_location(self):
        user_a, pass_a = self.create_user("a@test.com")
        self.authenticate("a@test.com", pass_a)
        merchant_a = self.create_merchant("Merchant A")

        res_loc = self.client.post("/api/v1/locations/",
                                   {"name": "Location A"},
                                   **self.merchant_headers(merchant_a))
        loc_id = res_loc.json()["id"]

        # user B
        self.client.credentials()
        user_b, pass_b = self.create_user("b@test.com")
        self.authenticate("b@test.com", pass_b)
        merchant_b = self.create_merchant("Merchant B")

        # User B tries deleting A's location
        res = self.client.delete(f"/api/v1/locations/{loc_id}/",
                                 **self.merchant_headers(merchant_b))
        self.assertEqual(res.status_code, 404)


    def test_unauthenticated_user_cannot_access_locations(self):
        user, password = self.create_user()
        self.authenticate(user.email, password)
        merchant = self.create_merchant("Merchant X")

        # Create a location
        loc_res = self.client.post("/api/v1/locations/",
                                   {"name": "Main Branch"},
                                   **self.merchant_headers(merchant))
        loc_id = loc_res.json()["id"]

        # Remove auth
        self.client.credentials()

        # List
        res1 = self.client.get("/api/v1/locations/", **self.merchant_headers(merchant))
        self.assertEqual(res1.status_code, 401)

        # Detail
        res2 = self.client.get(f"/api/v1/locations/{loc_id}/",
                               **self.merchant_headers(merchant))
        self.assertEqual(res2.status_code, 401)

        # Create
        res3 = self.client.post("/api/v1/locations/",
                                {"name": "Another"},
                                **self.merchant_headers(merchant))
        self.assertEqual(res3.status_code, 401)

    def test_locations_are_isolated_between_merchants(self):
        """
        Merchant A should not see Merchant B's locations,
        Merchant B should not see Merchant A's locations.
        """

        # ---------------- Merchant A ----------------
        _, p1, merchant_a = self.setup_user_and_merchant("locA@test.com", "Merchant A")

        loc_a1 = self.create_location(merchant_a, "A-Branch1")

        loc_a2 = self.create_location(merchant_a, "A-Branch2")

        # A fetches A's locations
        res_a = self.client.get("/api/v1/locations/", **self.merchant_headers(merchant_a))
        a_returned = [l["id"] for l in res_a.json()]
        self.assertCountEqual(a_returned, [loc_a1, loc_a2])

        # ---------------- Merchant B ----------------
        self.client.credentials()
        _, p2, merchant_b = self.setup_user_and_merchant("locB@test.com", "Merchant B")

        loc_b1 = self.create_location(merchant_b, "B-Branch1")

        # B fetches B's locations (should not see A)
        res_b = self.client.get("/api/v1/locations/", **self.merchant_headers(merchant_b))
        b_returned = [l["id"] for l in res_b.json()]
        self.assertCountEqual(b_returned, [loc_b1])

        # ---------------- Cross Access Attempts ----------------
        # A tries to fetch B’s locations
        self.client.credentials()
        self.authenticate("locA@test.com", p1)
        cross_a = self.client.get("/api/v1/locations/", **self.merchant_headers(merchant_b))
        self.assertEqual(cross_a.status_code, 403)

        # B tries to fetch A’s locations
        self.client.credentials()
        self.authenticate("locB@test.com", p2)
        cross_b = self.client.get("/api/v1/locations/", **self.merchant_headers(merchant_a))
        self.assertEqual(cross_b.status_code, 403)
