from rest_framework import status
from tests.base import BaseAPITest
from menus.models import Menu


class MenuTestMixin:
    """Shared helpers for menu tests."""

    def create_product_via_api(self, merchant_id, name="Burger", price=899,
                                product_type=1, location_id=None):
        """Create a product via API. If location_id given, auto-assigns to location."""
        headers = self.merchant_headers(merchant_id, location_id)
        res = self.client.post(
            "/api/v1/products/",
            {"name": name, "price": price, "product_type": product_type},
            format="json",
            **headers,
        )
        return res.json()["id"], res.json()["plu"]

    def create_product_location_via_api(self, merchant_id, product_plu, location_id,
                                         is_available=True, price_override=None, channels=None):
        headers = self.merchant_headers(merchant_id, location_id)
        data = {"is_available": is_available}
        if price_override is not None:
            data["price_override"] = price_override
        if channels is not None:
            data["channels"] = channels
        res = self.client.patch(
            f"/api/v1/products/{product_plu}/update_location_pricing/",
            data,
            format="json",
            **headers,
        )
        return res

    def menu_location_headers(self, merchant_id, location_id=None, channel_link_id=None):
        """Build headers with optional X-Location-ID and X-Channel-Link-ID."""
        headers = self.merchant_headers(merchant_id, location_id)
        if channel_link_id:
            headers["HTTP_X_CHANNEL_LINK_ID"] = str(channel_link_id)
        return headers

    def get_menu(self, menu_id):
        """GET a single menu — returns full nested response."""
        return self.client.get(f"/api/v1/menus/{menu_id}/", **self.headers)


class TestMenuCRUD(MenuTestMixin, BaseAPITest):
    """Test basic menu create / read / update / delete."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)

    def test_create_menu(self):
        res = self.client.post(
            "/api/v1/menus/",
            {"name": "Breakfast Menu", "description": "Morning items"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data["name"], "Breakfast Menu")
        self.assertEqual(data["categories"], [])
        self.assertEqual(data["availabilities"], [])
        self.assertEqual(data["locations"], [])

    def test_list_menus(self):
        self.client.post("/api/v1/menus/", {"name": "Menu A"}, format="json", **self.headers)
        self.client.post("/api/v1/menus/", {"name": "Menu B"}, format="json", **self.headers)
        res = self.client.get("/api/v1/menus/", **self.headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.json()), 2)

    def test_retrieve_menu_has_nested_data(self):
        """GET /menus/{id}/ returns categories, items, availabilities, locations."""
        res = self.client.post("/api/v1/menus/", {"name": "Full Menu"}, format="json", **self.headers)
        menu_id = res.json()["id"]

        res = self.get_menu(menu_id)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertIn("categories", data)
        self.assertIn("availabilities", data)
        self.assertIn("locations", data)

    def test_update_menu(self):
        res = self.client.post("/api/v1/menus/", {"name": "Old Name"}, format="json", **self.headers)
        menu_id = res.json()["id"]
        res = self.client.patch(
            f"/api/v1/menus/{menu_id}/",
            {"name": "New Name"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["name"], "New Name")

    def test_delete_menu(self):
        res = self.client.post("/api/v1/menus/", {"name": "Temp"}, format="json", **self.headers)
        menu_id = res.json()["id"]
        res = self.client.delete(f"/api/v1/menus/{menu_id}/", **self.headers)
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

    def test_requires_tenant_header(self):
        res = self.client.post("/api/v1/menus/", {"name": "No Tenant"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class TestMenuCategories(MenuTestMixin, BaseAPITest):
    """Test menu category endpoints."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)
        res = self.client.post("/api/v1/menus/", {"name": "Test Menu"}, format="json", **self.headers)
        self.menu_id = res.json()["id"]

    def test_add_category(self):
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/categories/",
            {"name": "Burgers", "sort_order": 1},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.json()["name"], "Burgers")

    def test_categories_visible_in_menu(self):
        self.client.post(
            f"/api/v1/menus/{self.menu_id}/categories/",
            {"name": "Cat A"},
            format="json",
            **self.headers,
        )
        self.client.post(
            f"/api/v1/menus/{self.menu_id}/categories/",
            {"name": "Cat B"},
            format="json",
            **self.headers,
        )
        res = self.get_menu(self.menu_id)
        self.assertEqual(len(res.json()["categories"]), 2)

    def test_duplicate_category_name_rejected(self):
        self.client.post(
            f"/api/v1/menus/{self.menu_id}/categories/",
            {"name": "Burgers"},
            format="json",
            **self.headers,
        )
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/categories/",
            {"name": "Burgers"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_category(self):
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/categories/",
            {"name": "Old"},
            format="json",
            **self.headers,
        )
        cat_id = res.json()["id"]
        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/categories/{cat_id}/",
            {"name": "New"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["name"], "New")

    def test_delete_category(self):
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/categories/",
            {"name": "ToDelete"},
            format="json",
            **self.headers,
        )
        cat_id = res.json()["id"]
        res = self.client.delete(
            f"/api/v1/menus/{self.menu_id}/categories/{cat_id}/",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)


class TestMenuItems(MenuTestMixin, BaseAPITest):
    """Test adding/removing products from a menu."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)

        # Create menu + category
        res = self.client.post("/api/v1/menus/", {"name": "Test Menu"}, format="json", **self.headers)
        self.menu_id = res.json()["id"]
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/categories/",
            {"name": "Mains"},
            format="json",
            **self.headers,
        )
        self.cat_id = res.json()["id"]

        # Create product in catalog via API (runs in tenant schema)
        self.product_id, self.product_plu = self.create_product_via_api(
            self.merchant_id, "Cheeseburger", 899
        )

    def test_add_item_to_menu(self):
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/items/",
            {"menu_category": self.cat_id, "product": self.product_id},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.json()["product_name"], "Cheeseburger")

    def test_items_nested_in_category(self):
        """Items appear nested under their category in the menu response."""
        self.client.post(
            f"/api/v1/menus/{self.menu_id}/items/",
            {"menu_category": self.cat_id, "product": self.product_id},
            format="json",
            **self.headers,
        )
        res = self.get_menu(self.menu_id)
        categories = res.json()["categories"]
        self.assertEqual(len(categories), 1)
        self.assertEqual(categories[0]["name"], "Mains")
        self.assertEqual(len(categories[0]["items"]), 1)
        self.assertEqual(categories[0]["items"][0]["product_name"], "Cheeseburger")

    def test_duplicate_product_in_menu_rejected(self):
        self.client.post(
            f"/api/v1/menus/{self.menu_id}/items/",
            {"menu_category": self.cat_id, "product": self.product_id},
            format="json",
            **self.headers,
        )
        # Create a second category
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/categories/",
            {"name": "Also Mains"},
            format="json",
            **self.headers,
        )
        cat2_id = res.json()["id"]
        # Try adding same product to second category
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/items/",
            {"menu_category": cat2_id, "product": self.product_id},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_item_with_price_override(self):
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/items/",
            {
                "menu_category": self.cat_id,
                "product": self.product_id,
                "price_override": 599,
            },
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.json()["price_override"], 599)

    def test_delete_item(self):
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/items/",
            {"menu_category": self.cat_id, "product": self.product_id},
            format="json",
            **self.headers,
        )
        item_id = res.json()["id"]
        res = self.client.delete(
            f"/api/v1/menus/{self.menu_id}/items/{item_id}/",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)


class TestMenuAvailability(MenuTestMixin, BaseAPITest):
    """Test menu availability (daypart) endpoints."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)
        res = self.client.post("/api/v1/menus/", {"name": "Breakfast"}, format="json", **self.headers)
        self.menu_id = res.json()["id"]

    def test_add_availability(self):
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/availabilities/",
            {"day_of_week": 0, "start_time": "07:00", "end_time": "12:00"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.json()["day_name"], "Monday")

    def test_invalid_time_range_rejected(self):
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/availabilities/",
            {"day_of_week": 0, "start_time": "12:00", "end_time": "07:00"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_availabilities_visible_in_menu(self):
        self.client.post(
            f"/api/v1/menus/{self.menu_id}/availabilities/",
            {"day_of_week": 0, "start_time": "07:00", "end_time": "12:00"},
            format="json",
            **self.headers,
        )
        self.client.post(
            f"/api/v1/menus/{self.menu_id}/availabilities/",
            {"day_of_week": 1, "start_time": "07:00", "end_time": "12:00"},
            format="json",
            **self.headers,
        )
        res = self.get_menu(self.menu_id)
        self.assertEqual(len(res.json()["availabilities"]), 2)

    def test_delete_availability(self):
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/availabilities/",
            {"day_of_week": 0, "start_time": "07:00", "end_time": "12:00"},
            format="json",
            **self.headers,
        )
        avail_id = res.json()["id"]
        res = self.client.delete(
            f"/api/v1/menus/{self.menu_id}/availabilities/{avail_id}/",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)


class TestMenuLocations(MenuTestMixin, BaseAPITest):
    """Test assigning locations and channels to menus via headers."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)
        self.location_id = self.create_location(self.merchant_id, "Downtown")

        res = self.client.post("/api/v1/menus/", {"name": "Main Menu"}, format="json", **self.headers)
        self.menu_id = res.json()["id"]

    def test_assign_location(self):
        headers = self.menu_location_headers(self.merchant_id, self.location_id)
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/locations/",
            format="json",
            **headers,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.json()["location_name"], "Downtown")

    def test_locations_visible_in_menu(self):
        headers = self.menu_location_headers(self.merchant_id, self.location_id)
        self.client.post(f"/api/v1/menus/{self.menu_id}/locations/", format="json", **headers)
        res = self.get_menu(self.menu_id)
        self.assertEqual(len(res.json()["locations"]), 1)
        self.assertEqual(res.json()["locations"][0]["location_name"], "Downtown")

    def test_assign_multiple_locations(self):
        loc2_id = self.create_location(self.merchant_id, "Airport")
        h1 = self.menu_location_headers(self.merchant_id, self.location_id)
        h2 = self.menu_location_headers(self.merchant_id, loc2_id)
        self.client.post(f"/api/v1/menus/{self.menu_id}/locations/", format="json", **h1)
        self.client.post(f"/api/v1/menus/{self.menu_id}/locations/", format="json", **h2)
        res = self.get_menu(self.menu_id)
        self.assertEqual(len(res.json()["locations"]), 2)

    def test_remove_location(self):
        headers = self.menu_location_headers(self.merchant_id, self.location_id)
        self.client.post(f"/api/v1/menus/{self.menu_id}/locations/", format="json", **headers)
        res = self.client.delete(f"/api/v1/menus/{self.menu_id}/locations/", **headers)
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

    def test_assign_location_requires_header(self):
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/locations/",
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_assign_channel_to_location(self):
        # Assign location first
        loc_headers = self.menu_location_headers(self.merchant_id, self.location_id)
        self.client.post(f"/api/v1/menus/{self.menu_id}/locations/", format="json", **loc_headers)

        # Create channel + link
        channel = self.create_channel(slug="ubereats", display_name="UberEats", channel_type="marketplace")
        cl_id = self.create_channel_link(channel, self.location_id, self.merchant_id)

        # Assign channel via header
        ch_headers = self.menu_location_headers(self.merchant_id, self.location_id, cl_id)
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/channels/",
            format="json",
            **ch_headers,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.json()["status"], "draft")

    def test_channels_nested_in_location(self):
        """Channels appear nested under their location in the menu response."""
        loc_headers = self.menu_location_headers(self.merchant_id, self.location_id)
        self.client.post(f"/api/v1/menus/{self.menu_id}/locations/", format="json", **loc_headers)

        channel = self.create_channel(slug="ubereats", display_name="UberEats", channel_type="marketplace")
        cl_id = self.create_channel_link(channel, self.location_id, self.merchant_id)
        ch_headers = self.menu_location_headers(self.merchant_id, self.location_id, cl_id)
        self.client.post(f"/api/v1/menus/{self.menu_id}/channels/", format="json", **ch_headers)

        res = self.get_menu(self.menu_id)
        locations = res.json()["locations"]
        self.assertEqual(len(locations), 1)
        self.assertEqual(len(locations[0]["channels"]), 1)
        self.assertEqual(locations[0]["channels"][0]["channel_name"], "UberEats")

    def test_remove_channel_from_location(self):
        loc_headers = self.menu_location_headers(self.merchant_id, self.location_id)
        self.client.post(f"/api/v1/menus/{self.menu_id}/locations/", format="json", **loc_headers)

        channel = self.create_channel(slug="ubereats", display_name="UberEats", channel_type="marketplace")
        cl_id = self.create_channel_link(channel, self.location_id, self.merchant_id)
        ch_headers = self.menu_location_headers(self.merchant_id, self.location_id, cl_id)
        self.client.post(f"/api/v1/menus/{self.menu_id}/channels/", format="json", **ch_headers)

        res = self.client.delete(f"/api/v1/menus/{self.menu_id}/channels/", **ch_headers)
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

        res = self.get_menu(self.menu_id)
        self.assertEqual(len(res.json()["locations"][0]["channels"]), 0)


class TestMenuDuplicate(MenuTestMixin, BaseAPITest):
    """Test menu duplication."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)

        # Create menu with categories and items
        res = self.client.post("/api/v1/menus/", {"name": "Original"}, format="json", **self.headers)
        self.menu_id = res.json()["id"]

        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/categories/",
            {"name": "Burgers"},
            format="json",
            **self.headers,
        )
        cat_id = res.json()["id"]

        self.product_id, self.product_plu = self.create_product_via_api(
            self.merchant_id, "Cheeseburger", 899
        )
        self.client.post(
            f"/api/v1/menus/{self.menu_id}/items/",
            {"menu_category": cat_id, "product": self.product_id},
            format="json",
            **self.headers,
        )

    def test_duplicate_menu(self):
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/duplicate/",
            {"name": "Copy of Original"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertNotEqual(data["id"], self.menu_id)
        self.assertEqual(data["name"], "Copy of Original")
        self.assertFalse(data["is_active"])  # Copies start inactive

        # Nested data should be in the response directly
        self.assertEqual(len(data["categories"]), 1)
        self.assertEqual(data["categories"][0]["name"], "Burgers")
        self.assertEqual(len(data["categories"][0]["items"]), 1)
        self.assertEqual(data["categories"][0]["items"][0]["product_name"], "Cheeseburger")


class TestMenuBulkOperations(MenuTestMixin, BaseAPITest):
    """Test bulk update and bulk remove operations."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)

        res = self.client.post("/api/v1/menus/", {"name": "Bulk Test"}, format="json", **self.headers)
        self.menu_id = res.json()["id"]

        # Create two categories
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/categories/",
            {"name": "Starters", "sort_order": 1},
            format="json",
            **self.headers,
        )
        self.cat1_id = res.json()["id"]

        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/categories/",
            {"name": "Mains", "sort_order": 2},
            format="json",
            **self.headers,
        )
        self.cat2_id = res.json()["id"]

        # Create 3 products and add them to category 1
        self.item_ids = []
        for name in ["Soup", "Salad", "Bread"]:
            prod_id, _ = self.create_product_via_api(self.merchant_id, name, 500)
            res = self.client.post(
                f"/api/v1/menus/{self.menu_id}/items/",
                {"menu_category": self.cat1_id, "product": prod_id, "sort_order": len(self.item_ids)},
                format="json",
                **self.headers,
            )
            self.item_ids.append(res.json()["id"])

    def test_bulk_update_item_sort_order(self):
        """Reorder items in a single call."""
        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/items/bulk/",
            {
                "items": [
                    {"id": self.item_ids[0], "sort_order": 3},
                    {"id": self.item_ids[1], "sort_order": 1},
                    {"id": self.item_ids[2], "sort_order": 2},
                ]
            },
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["updated"], 3)

        # Verify via menu response
        menu = self.get_menu(self.menu_id).json()
        items = menu["categories"][0]["items"]
        sort_orders = {i["id"]: i["sort_order"] for i in items}
        self.assertEqual(sort_orders[self.item_ids[0]], 3)
        self.assertEqual(sort_orders[self.item_ids[1]], 1)
        self.assertEqual(sort_orders[self.item_ids[2]], 2)

    def test_bulk_update_item_visibility(self):
        """Toggle visibility on multiple items."""
        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/items/bulk/",
            {
                "items": [
                    {"id": self.item_ids[0], "is_visible": False},
                    {"id": self.item_ids[1], "is_visible": False},
                ]
            },
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["updated"], 2)

        menu = self.get_menu(self.menu_id).json()
        items = menu["categories"][0]["items"]
        visibility = {i["id"]: i["is_visible"] for i in items}
        self.assertFalse(visibility[self.item_ids[0]])
        self.assertFalse(visibility[self.item_ids[1]])
        self.assertTrue(visibility[self.item_ids[2]])

    def test_bulk_update_item_price_override(self):
        """Set price overrides on multiple items."""
        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/items/bulk/",
            {
                "items": [
                    {"id": self.item_ids[0], "price_override": 399},
                    {"id": self.item_ids[1], "price_override": 499},
                ]
            },
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        menu = self.get_menu(self.menu_id).json()
        items = menu["categories"][0]["items"]
        prices = {i["id"]: i["price_override"] for i in items}
        self.assertEqual(prices[self.item_ids[0]], 399)
        self.assertEqual(prices[self.item_ids[1]], 499)
        self.assertIsNone(prices[self.item_ids[2]])

    def test_bulk_move_item_to_different_category(self):
        """Move an item from one category to another."""
        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/items/bulk/",
            {
                "items": [
                    {"id": self.item_ids[0], "menu_category": self.cat2_id},
                ]
            },
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        menu = self.get_menu(self.menu_id).json()
        cat1_items = [c for c in menu["categories"] if c["id"] == self.cat1_id][0]["items"]
        cat2_items = [c for c in menu["categories"] if c["id"] == self.cat2_id][0]["items"]
        self.assertEqual(len(cat1_items), 2)
        self.assertEqual(len(cat2_items), 1)
        self.assertEqual(cat2_items[0]["id"], self.item_ids[0])

    def test_bulk_update_rejects_invalid_item(self):
        """Referencing a non-existent item returns an error."""
        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/items/bulk/",
            {
                "items": [
                    {"id": "00000000-0000-0000-0000-000000000000", "sort_order": 1},
                ]
            },
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_remove_items(self):
        """Remove multiple items in one call."""
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/items/bulk-remove/",
            {"item_ids": [self.item_ids[0], self.item_ids[1]]},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["deleted"], 2)

        menu = self.get_menu(self.menu_id).json()
        items = menu["categories"][0]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], self.item_ids[2])

    def test_bulk_update_category_sort_order(self):
        """Reorder categories in one call."""
        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/categories/bulk/",
            {
                "categories": [
                    {"id": self.cat1_id, "sort_order": 2},
                    {"id": self.cat2_id, "sort_order": 1},
                ]
            },
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["updated"], 2)

    def test_bulk_update_category_name(self):
        """Rename categories in one call."""
        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/categories/bulk/",
            {
                "categories": [
                    {"id": self.cat1_id, "name": "Appetizers"},
                ]
            },
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        menu = self.get_menu(self.menu_id).json()
        names = {c["id"]: c["name"] for c in menu["categories"]}
        self.assertEqual(names[self.cat1_id], "Appetizers")
        self.assertEqual(names[self.cat2_id], "Mains")


class TestMenuPublish(MenuTestMixin, BaseAPITest):
    """Test the publish workflow."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)
        self.location_id = self.create_location(self.merchant_id, "Downtown")

        # Create product via API with location (auto-assigns to location)
        self.product_id, self.product_plu = self.create_product_via_api(
            self.merchant_id, "Burger", 999, location_id=self.location_id
        )

        # Create menu
        res = self.client.post("/api/v1/menus/", {"name": "Lunch"}, format="json", **self.headers)
        self.menu_id = res.json()["id"]

        # Add category + item
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/categories/",
            {"name": "Mains"},
            format="json",
            **self.headers,
        )
        cat_id = res.json()["id"]

        self.client.post(
            f"/api/v1/menus/{self.menu_id}/items/",
            {"menu_category": cat_id, "product": self.product_id},
            format="json",
            **self.headers,
        )

        # Assign location via header
        loc_headers = self.menu_location_headers(self.merchant_id, self.location_id)
        self.client.post(f"/api/v1/menus/{self.menu_id}/locations/", format="json", **loc_headers)

        # Create channel + link + assign channel via header
        self.channel = self.create_channel(
            slug="internal_pos", display_name="Internal POS"
        )
        self.cl_id = self.create_channel_link(
            self.channel, self.location_id, self.merchant_id
        )
        ch_headers = self.menu_location_headers(self.merchant_id, self.location_id, self.cl_id)
        self.client.post(
            f"/api/v1/menus/{self.menu_id}/channels/",
            format="json",
            **ch_headers,
        )

    def test_publish_menu(self):
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/publish/",
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data["published"], 1)
        self.assertEqual(data["results"][0]["location"], "Downtown")

    def test_publish_inactive_menu_rejected(self):
        self.client.patch(
            f"/api/v1/menus/{self.menu_id}/",
            {"is_active": False},
            format="json",
            **self.headers,
        )
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/publish/",
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_publish_status(self):
        self.client.post(
            f"/api/v1/menus/{self.menu_id}/publish/",
            format="json",
            **self.headers,
        )
        res = self.client.get(
            f"/api/v1/menus/{self.menu_id}/publish-status/",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.json()), 1)

    def test_publish_skips_unavailable_products(self):
        self.create_product_location_via_api(
            self.merchant_id, self.product_plu, self.location_id, is_available=False
        )

        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/publish/",
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data["published"], 1)


class TestMenuPublishPricing(MenuTestMixin, BaseAPITest):
    """Test that publish resolves prices correctly through the fallback chain."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)
        self.location_id = self.create_location(self.merchant_id, "Downtown")

        self.product_id, self.product_plu = self.create_product_via_api(
            self.merchant_id, "Burger", 899, location_id=self.location_id
        )

        self.channel = self.create_channel(
            slug="ubereats", display_name="UberEats", channel_type="marketplace"
        )
        self.cl_id = self.create_channel_link(
            self.channel, self.location_id, self.merchant_id
        )

    def _setup_menu_with_item(self, price_override=None):
        """Helper to create full menu -> category -> item -> location -> channel."""
        res = self.client.post(
            "/api/v1/menus/", {"name": "Test"}, format="json", **self.headers
        )
        menu_id = res.json()["id"]

        res = self.client.post(
            f"/api/v1/menus/{menu_id}/categories/",
            {"name": "Mains"},
            format="json",
            **self.headers,
        )
        cat_id = res.json()["id"]

        item_data = {"menu_category": cat_id, "product": self.product_id}
        if price_override is not None:
            item_data["price_override"] = price_override
        self.client.post(
            f"/api/v1/menus/{menu_id}/items/", item_data, format="json", **self.headers
        )

        # Assign location via header
        loc_headers = self.menu_location_headers(self.merchant_id, self.location_id)
        self.client.post(f"/api/v1/menus/{menu_id}/locations/", format="json", **loc_headers)

        # Assign channel via header
        ch_headers = self.menu_location_headers(self.merchant_id, self.location_id, self.cl_id)
        self.client.post(f"/api/v1/menus/{menu_id}/channels/", format="json", **ch_headers)

        return menu_id

    def _get_published_price(self, menu_id):
        """Publish and return the first item's price from the snapshot."""
        res = self.client.post(f"/api/v1/menus/{menu_id}/publish/", format="json", **self.headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        snapshot = res.json()["results"][0]["snapshot"]
        return snapshot["categories"][0]["items"][0]["price"]

    def test_price_uses_catalog_base(self):
        """No overrides -> falls back to Product.price."""
        menu_id = self._setup_menu_with_item()
        price = self._get_published_price(menu_id)
        self.assertEqual(price, 899)

    def test_price_uses_location_override(self):
        """ProductLocation.price_override takes precedence over Product.price."""
        self.create_product_location_via_api(
            self.merchant_id, self.product_plu, self.location_id,
            price_override=1099,
        )
        menu_id = self._setup_menu_with_item()
        price = self._get_published_price(menu_id)
        self.assertEqual(price, 1099)

    def test_price_uses_channel_override(self):
        """Channel price in ProductLocation.channels takes precedence."""
        self.create_product_location_via_api(
            self.merchant_id, self.product_plu, self.location_id,
            price_override=1099,
            channels={"ubereats": {"price": 1299, "is_available": True}},
        )
        menu_id = self._setup_menu_with_item()
        price = self._get_published_price(menu_id)
        self.assertEqual(price, 1299)

    def test_price_uses_menu_override(self):
        """MenuItem.price_override is highest priority."""
        self.create_product_location_via_api(
            self.merchant_id, self.product_plu, self.location_id,
            price_override=1099,
            channels={"ubereats": {"price": 1299, "is_available": True}},
        )
        menu_id = self._setup_menu_with_item(price_override=599)
        price = self._get_published_price(menu_id)
        self.assertEqual(price, 599)


# ═══════════════════════════════════════════════════════════════
# Edge cases & error paths
# ═══════════════════════════════════════════════════════════════


class TestMenuErrorPaths(MenuTestMixin, BaseAPITest):
    """Test 404 and validation error paths."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)

        res = self.client.post("/api/v1/menus/", {"name": "Test Menu"}, format="json", **self.headers)
        self.menu_id = res.json()["id"]

        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/categories/",
            {"name": "Mains"},
            format="json",
            **self.headers,
        )
        self.cat_id = res.json()["id"]

        self.product_id, self.product_plu = self.create_product_via_api(
            self.merchant_id, "Burger", 899
        )

    # ── 404 paths ────────────────────────────────────────────

    def test_patch_nonexistent_category(self):
        fake = "00000000-0000-0000-0000-000000000000"
        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/categories/{fake}/",
            {"name": "Nope"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_nonexistent_category(self):
        fake = "00000000-0000-0000-0000-000000000000"
        res = self.client.delete(
            f"/api/v1/menus/{self.menu_id}/categories/{fake}/",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_nonexistent_item(self):
        fake = "00000000-0000-0000-0000-000000000000"
        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/items/{fake}/",
            {"sort_order": 5},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_nonexistent_item(self):
        fake = "00000000-0000-0000-0000-000000000000"
        res = self.client.delete(
            f"/api/v1/menus/{self.menu_id}/items/{fake}/",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_nonexistent_availability(self):
        fake = "00000000-0000-0000-0000-000000000000"
        res = self.client.delete(
            f"/api/v1/menus/{self.menu_id}/availabilities/{fake}/",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_remove_unassigned_location(self):
        location_id = self.create_location(self.merchant_id, "Nowhere")
        headers = self.menu_location_headers(self.merchant_id, location_id)
        res = self.client.delete(f"/api/v1/menus/{self.menu_id}/locations/", **headers)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_channel_on_unassigned_location(self):
        """POST channel when location is not assigned to menu."""
        location_id = self.create_location(self.merchant_id, "Nowhere")
        channel = self.create_channel(slug="ubereats", display_name="UberEats", channel_type="marketplace")
        cl_id = self.create_channel_link(channel, location_id, self.merchant_id)
        headers = self.menu_location_headers(self.merchant_id, location_id, cl_id)
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/channels/",
            format="json",
            **headers,
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_remove_unassigned_channel(self):
        """DELETE channel that's not assigned to this menu-location."""
        location_id = self.create_location(self.merchant_id, "Downtown")
        loc_headers = self.menu_location_headers(self.merchant_id, location_id)
        self.client.post(f"/api/v1/menus/{self.menu_id}/locations/", format="json", **loc_headers)

        channel = self.create_channel(slug="ubereats", display_name="UberEats", channel_type="marketplace")
        cl_id = self.create_channel_link(channel, location_id, self.merchant_id)
        headers = self.menu_location_headers(self.merchant_id, location_id, cl_id)
        res = self.client.delete(f"/api/v1/menus/{self.menu_id}/channels/", **headers)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_channel_requires_location_header(self):
        """POST channel without X-Location-ID header."""
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/channels/",
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_channel_requires_channel_link_header(self):
        """POST channel without X-Channel-Link-ID header."""
        location_id = self.create_location(self.merchant_id, "Downtown")
        loc_headers = self.menu_location_headers(self.merchant_id, location_id)
        self.client.post(f"/api/v1/menus/{self.menu_id}/locations/", format="json", **loc_headers)
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/channels/",
            format="json",
            **loc_headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Cross-menu validation ────────────────────────────────

    def test_item_with_category_from_different_menu(self):
        """Adding an item with a category from another menu is rejected."""
        res = self.client.post("/api/v1/menus/", {"name": "Other Menu"}, format="json", **self.headers)
        other_menu_id = res.json()["id"]
        res = self.client.post(
            f"/api/v1/menus/{other_menu_id}/categories/",
            {"name": "Other Cat"},
            format="json",
            **self.headers,
        )
        other_cat_id = res.json()["id"]

        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/items/",
            {"menu_category": other_cat_id, "product": self.product_id},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class TestMenuUniquenessConstraints(MenuTestMixin, BaseAPITest):
    """Test duplicate assignment rejection."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)
        self.location_id = self.create_location(self.merchant_id, "Downtown")

        res = self.client.post("/api/v1/menus/", {"name": "Test"}, format="json", **self.headers)
        self.menu_id = res.json()["id"]

    def test_duplicate_location_assignment_rejected(self):
        headers = self.menu_location_headers(self.merchant_id, self.location_id)
        res1 = self.client.post(f"/api/v1/menus/{self.menu_id}/locations/", format="json", **headers)
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        res2 = self.client.post(f"/api/v1/menus/{self.menu_id}/locations/", format="json", **headers)
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_channel_assignment_rejected(self):
        loc_headers = self.menu_location_headers(self.merchant_id, self.location_id)
        self.client.post(f"/api/v1/menus/{self.menu_id}/locations/", format="json", **loc_headers)

        channel = self.create_channel(slug="ubereats", display_name="UberEats", channel_type="marketplace")
        cl_id = self.create_channel_link(channel, self.location_id, self.merchant_id)
        ch_headers = self.menu_location_headers(self.merchant_id, self.location_id, cl_id)

        res1 = self.client.post(f"/api/v1/menus/{self.menu_id}/channels/", format="json", **ch_headers)
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        res2 = self.client.post(f"/api/v1/menus/{self.menu_id}/channels/", format="json", **ch_headers)
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)


class TestMenuAvailabilityEdgeCases(MenuTestMixin, BaseAPITest):
    """Test availability validation edge cases."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)
        res = self.client.post("/api/v1/menus/", {"name": "Test"}, format="json", **self.headers)
        self.menu_id = res.json()["id"]

    def test_end_date_before_start_date_rejected(self):
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/availabilities/",
            {
                "day_of_week": 0,
                "start_time": "07:00",
                "end_time": "12:00",
                "start_date": "2026-09-01",
                "end_date": "2026-03-01",
            },
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_seasonal_availability_with_dates(self):
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/availabilities/",
            {
                "day_of_week": 5,
                "start_time": "18:00",
                "end_time": "23:00",
                "start_date": "2026-06-01",
                "end_date": "2026-08-31",
            },
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data["start_date"], "2026-06-01")
        self.assertEqual(data["end_date"], "2026-08-31")

        # Verify it shows in menu
        menu = self.get_menu(self.menu_id).json()
        avail = menu["availabilities"][0]
        self.assertEqual(avail["start_date"], "2026-06-01")


class TestMenuCascadeDeletes(MenuTestMixin, BaseAPITest):
    """Test that deleting parents cascades correctly."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)
        self.location_id = self.create_location(self.merchant_id, "Downtown")

    def test_delete_category_cascades_items(self):
        """Deleting a category removes all items in it."""
        res = self.client.post("/api/v1/menus/", {"name": "Test"}, format="json", **self.headers)
        menu_id = res.json()["id"]

        res = self.client.post(
            f"/api/v1/menus/{menu_id}/categories/",
            {"name": "Burgers"},
            format="json",
            **self.headers,
        )
        cat_id = res.json()["id"]

        # Add 2 items
        for name in ["Burger A", "Burger B"]:
            prod_id, _ = self.create_product_via_api(self.merchant_id, name, 899)
            self.client.post(
                f"/api/v1/menus/{menu_id}/items/",
                {"menu_category": cat_id, "product": prod_id},
                format="json",
                **self.headers,
            )

        # Verify 2 items exist
        menu = self.get_menu(menu_id).json()
        self.assertEqual(len(menu["categories"][0]["items"]), 2)

        # Delete category
        self.client.delete(f"/api/v1/menus/{menu_id}/categories/{cat_id}/", **self.headers)

        # Verify empty
        menu = self.get_menu(menu_id).json()
        self.assertEqual(len(menu["categories"]), 0)

    def test_delete_menu_cascades_everything(self):
        """Deleting a menu removes categories, items, locations, channels."""
        res = self.client.post("/api/v1/menus/", {"name": "Full"}, format="json", **self.headers)
        menu_id = res.json()["id"]

        # Add category + item
        res = self.client.post(
            f"/api/v1/menus/{menu_id}/categories/",
            {"name": "Cat"},
            format="json",
            **self.headers,
        )
        cat_id = res.json()["id"]
        prod_id, _ = self.create_product_via_api(self.merchant_id, "Item", 500)
        self.client.post(
            f"/api/v1/menus/{menu_id}/items/",
            {"menu_category": cat_id, "product": prod_id},
            format="json",
            **self.headers,
        )

        # Assign location + channel
        loc_headers = self.menu_location_headers(self.merchant_id, self.location_id)
        self.client.post(f"/api/v1/menus/{menu_id}/locations/", format="json", **loc_headers)
        channel = self.create_channel(slug="ubereats", display_name="UberEats", channel_type="marketplace")
        cl_id = self.create_channel_link(channel, self.location_id, self.merchant_id)
        ch_headers = self.menu_location_headers(self.merchant_id, self.location_id, cl_id)
        self.client.post(f"/api/v1/menus/{menu_id}/channels/", format="json", **ch_headers)

        # Delete menu
        res = self.client.delete(f"/api/v1/menus/{menu_id}/", **self.headers)
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

        # Verify gone
        res = self.client.get(f"/api/v1/menus/{menu_id}/", **self.headers)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_remove_location_cascades_channels(self):
        """Removing a location from a menu removes its channel assignments."""
        res = self.client.post("/api/v1/menus/", {"name": "Test"}, format="json", **self.headers)
        menu_id = res.json()["id"]

        # Assign location
        loc_headers = self.menu_location_headers(self.merchant_id, self.location_id)
        self.client.post(f"/api/v1/menus/{menu_id}/locations/", format="json", **loc_headers)

        # Assign 2 channels
        ch1 = self.create_channel(slug="ubereats", display_name="UberEats", channel_type="marketplace")
        cl1_id = self.create_channel_link(ch1, self.location_id, self.merchant_id)
        ch2 = self.create_channel(slug="doordash", display_name="DoorDash", channel_type="marketplace")
        cl2_id = self.create_channel_link(ch2, self.location_id, self.merchant_id)

        h1 = self.menu_location_headers(self.merchant_id, self.location_id, cl1_id)
        h2 = self.menu_location_headers(self.merchant_id, self.location_id, cl2_id)
        self.client.post(f"/api/v1/menus/{menu_id}/channels/", format="json", **h1)
        self.client.post(f"/api/v1/menus/{menu_id}/channels/", format="json", **h2)

        # Verify 2 channels
        menu = self.get_menu(menu_id).json()
        self.assertEqual(len(menu["locations"][0]["channels"]), 2)

        # Remove location
        self.client.delete(f"/api/v1/menus/{menu_id}/locations/", **loc_headers)

        # Verify location and channels gone
        menu = self.get_menu(menu_id).json()
        self.assertEqual(len(menu["locations"]), 0)


class TestMenuPublishEdgeCases(MenuTestMixin, BaseAPITest):
    """Test publishing edge cases."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)
        self.location_id = self.create_location(self.merchant_id, "Downtown")

    def _create_full_menu(self, product_name="Burger", product_price=999,
                          item_visible=True, channel_slug="internal_pos",
                          channel_name="Internal POS", channel_type="pos"):
        """Helper to create a full publishable menu and return IDs."""
        prod_id, prod_plu = self.create_product_via_api(
            self.merchant_id, product_name, product_price, location_id=self.location_id
        )

        res = self.client.post("/api/v1/menus/", {"name": "Test"}, format="json", **self.headers)
        menu_id = res.json()["id"]

        res = self.client.post(
            f"/api/v1/menus/{menu_id}/categories/",
            {"name": "Mains"},
            format="json",
            **self.headers,
        )
        cat_id = res.json()["id"]

        self.client.post(
            f"/api/v1/menus/{menu_id}/items/",
            {"menu_category": cat_id, "product": prod_id, "is_visible": item_visible},
            format="json",
            **self.headers,
        )

        loc_headers = self.menu_location_headers(self.merchant_id, self.location_id)
        self.client.post(f"/api/v1/menus/{menu_id}/locations/", format="json", **loc_headers)

        channel = self.create_channel(slug=channel_slug, display_name=channel_name, channel_type=channel_type)
        cl_id = self.create_channel_link(channel, self.location_id, self.merchant_id)
        ch_headers = self.menu_location_headers(self.merchant_id, self.location_id, cl_id)
        self.client.post(f"/api/v1/menus/{menu_id}/channels/", format="json", **ch_headers)

        return menu_id, prod_id, prod_plu

    def test_publish_with_no_locations(self):
        """Publishing a menu with no locations returns 0 results."""
        res = self.client.post("/api/v1/menus/", {"name": "Empty"}, format="json", **self.headers)
        menu_id = res.json()["id"]

        res = self.client.post(f"/api/v1/menus/{menu_id}/publish/", format="json", **self.headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["published"], 0)
        self.assertEqual(res.json()["results"], [])

    def test_publish_with_no_channels(self):
        """Location assigned but no channels → 0 results."""
        res = self.client.post("/api/v1/menus/", {"name": "No Channels"}, format="json", **self.headers)
        menu_id = res.json()["id"]

        loc_headers = self.menu_location_headers(self.merchant_id, self.location_id)
        self.client.post(f"/api/v1/menus/{menu_id}/locations/", format="json", **loc_headers)

        res = self.client.post(f"/api/v1/menus/{menu_id}/publish/", format="json", **self.headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["published"], 0)

    def test_publish_skips_invisible_menu_item(self):
        """Items with is_visible=False are excluded from the snapshot."""
        menu_id, _, _ = self._create_full_menu(item_visible=False)

        res = self.client.post(f"/api/v1/menus/{menu_id}/publish/", format="json", **self.headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        snapshot = res.json()["results"][0]["snapshot"]
        # No categories in payload because the only item was invisible
        self.assertEqual(len(snapshot["categories"]), 0)

    def test_publish_snapshot_structure(self):
        """Verify the snapshot has all expected top-level keys."""
        menu_id, _, _ = self._create_full_menu()

        res = self.client.post(f"/api/v1/menus/{menu_id}/publish/", format="json", **self.headers)
        snapshot = res.json()["results"][0]["snapshot"]

        expected_keys = {"menu_name", "location_id", "location_name", "channel",
                         "categories", "availabilities", "skipped"}
        self.assertEqual(set(snapshot.keys()), expected_keys)

    def test_publish_to_multiple_locations_and_channels(self):
        """Publish a single menu to 2 locations x 1 channel each."""
        loc2_id = self.create_location(self.merchant_id, "Airport")

        prod_id, _ = self.create_product_via_api(
            self.merchant_id, "Burger", 999, location_id=self.location_id
        )
        # Also assign product to loc2
        self.create_product_via_api(self.merchant_id, "Burger2", 999, location_id=loc2_id)

        res = self.client.post("/api/v1/menus/", {"name": "Multi"}, format="json", **self.headers)
        menu_id = res.json()["id"]

        res = self.client.post(
            f"/api/v1/menus/{menu_id}/categories/",
            {"name": "Mains"},
            format="json",
            **self.headers,
        )
        cat_id = res.json()["id"]
        self.client.post(
            f"/api/v1/menus/{menu_id}/items/",
            {"menu_category": cat_id, "product": prod_id},
            format="json",
            **self.headers,
        )

        # Assign 2 locations
        h1 = self.menu_location_headers(self.merchant_id, self.location_id)
        h2 = self.menu_location_headers(self.merchant_id, loc2_id)
        self.client.post(f"/api/v1/menus/{menu_id}/locations/", format="json", **h1)
        self.client.post(f"/api/v1/menus/{menu_id}/locations/", format="json", **h2)

        # Each location gets a channel
        ch1 = self.create_channel(slug="ubereats", display_name="UberEats", channel_type="marketplace")
        cl1_id = self.create_channel_link(ch1, self.location_id, self.merchant_id)
        ch2 = self.create_channel(slug="doordash", display_name="DoorDash", channel_type="marketplace")
        cl2_id = self.create_channel_link(ch2, loc2_id, self.merchant_id)

        ch1_headers = self.menu_location_headers(self.merchant_id, self.location_id, cl1_id)
        ch2_headers = self.menu_location_headers(self.merchant_id, loc2_id, cl2_id)
        self.client.post(f"/api/v1/menus/{menu_id}/channels/", format="json", **ch1_headers)
        self.client.post(f"/api/v1/menus/{menu_id}/channels/", format="json", **ch2_headers)

        res = self.client.post(f"/api/v1/menus/{menu_id}/publish/", format="json", **self.headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["published"], 2)
        locations = {r["location"] for r in res.json()["results"]}
        self.assertEqual(locations, {"Downtown", "Airport"})


class TestMenuDuplicateEdgeCases(MenuTestMixin, BaseAPITest):
    """Test menu duplication edge cases."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)
        self.location_id = self.create_location(self.merchant_id, "Downtown")

    def test_duplicate_auto_generates_name(self):
        """Duplicate without providing a name creates 'Menu (Copy)'."""
        res = self.client.post("/api/v1/menus/", {"name": "Lunch"}, format="json", **self.headers)
        menu_id = res.json()["id"]

        res = self.client.post(
            f"/api/v1/menus/{menu_id}/duplicate/",
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.json()["name"], "Lunch (Copy)")

    def test_duplicate_copies_availabilities(self):
        res = self.client.post("/api/v1/menus/", {"name": "Timed"}, format="json", **self.headers)
        menu_id = res.json()["id"]

        self.client.post(
            f"/api/v1/menus/{menu_id}/availabilities/",
            {"day_of_week": 0, "start_time": "07:00", "end_time": "12:00"},
            format="json",
            **self.headers,
        )
        self.client.post(
            f"/api/v1/menus/{menu_id}/availabilities/",
            {"day_of_week": 1, "start_time": "11:00", "end_time": "14:00"},
            format="json",
            **self.headers,
        )

        res = self.client.post(
            f"/api/v1/menus/{menu_id}/duplicate/",
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(res.json()["availabilities"]), 2)

    def test_duplicate_does_not_copy_locations(self):
        """Locations and channels should NOT be copied to the new menu."""
        res = self.client.post("/api/v1/menus/", {"name": "Located"}, format="json", **self.headers)
        menu_id = res.json()["id"]

        loc_headers = self.menu_location_headers(self.merchant_id, self.location_id)
        self.client.post(f"/api/v1/menus/{menu_id}/locations/", format="json", **loc_headers)

        res = self.client.post(
            f"/api/v1/menus/{menu_id}/duplicate/",
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(res.json()["locations"]), 0)

    def test_duplicate_empty_menu(self):
        res = self.client.post("/api/v1/menus/", {"name": "Empty"}, format="json", **self.headers)
        menu_id = res.json()["id"]

        res = self.client.post(
            f"/api/v1/menus/{menu_id}/duplicate/",
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(len(data["categories"]), 0)
        self.assertEqual(len(data["availabilities"]), 0)
        self.assertEqual(len(data["locations"]), 0)


class TestMenuBulkEdgeCases(MenuTestMixin, BaseAPITest):
    """Test bulk operation edge cases."""

    def setUp(self):
        self.user, self.pwd, self.merchant_id = self.setup_user_and_merchant()
        self.headers = self.merchant_headers(self.merchant_id)

        res = self.client.post("/api/v1/menus/", {"name": "Test"}, format="json", **self.headers)
        self.menu_id = res.json()["id"]

        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/categories/",
            {"name": "Cat"},
            format="json",
            **self.headers,
        )
        self.cat_id = res.json()["id"]

        prod_id, _ = self.create_product_via_api(self.merchant_id, "Item", 500)
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/items/",
            {"menu_category": self.cat_id, "product": prod_id},
            format="json",
            **self.headers,
        )
        self.item_id = res.json()["id"]

    def test_bulk_update_disallowed_field_rejected(self):
        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/items/bulk/",
            {"items": [{"id": self.item_id, "created_at": "2020-01-01"}]},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not allowed", res.json()["error"])

    def test_bulk_update_empty_list_rejected(self):
        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/items/bulk/",
            {"items": []},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_update_missing_id_rejected(self):
        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/items/bulk/",
            {"items": [{"sort_order": 5}]},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_move_to_category_from_different_menu(self):
        """Moving items to a category from another menu is rejected."""
        res = self.client.post("/api/v1/menus/", {"name": "Other"}, format="json", **self.headers)
        other_menu_id = res.json()["id"]
        res = self.client.post(
            f"/api/v1/menus/{other_menu_id}/categories/",
            {"name": "Other Cat"},
            format="json",
            **self.headers,
        )
        other_cat_id = res.json()["id"]

        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/items/bulk/",
            {"items": [{"id": self.item_id, "menu_category": other_cat_id}]},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not found in this menu", res.json()["error"])

    def test_bulk_remove_ids_from_different_menu(self):
        """Trying to remove items from a different menu deletes 0."""
        res = self.client.post("/api/v1/menus/", {"name": "Other"}, format="json", **self.headers)
        other_menu_id = res.json()["id"]
        res = self.client.post(
            f"/api/v1/menus/{other_menu_id}/categories/",
            {"name": "Cat"},
            format="json",
            **self.headers,
        )
        other_cat_id = res.json()["id"]
        prod_id, _ = self.create_product_via_api(self.merchant_id, "Other Item", 300)
        res = self.client.post(
            f"/api/v1/menus/{other_menu_id}/items/",
            {"menu_category": other_cat_id, "product": prod_id},
            format="json",
            **self.headers,
        )
        other_item_id = res.json()["id"]

        # Try removing the other menu's item from this menu
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/items/bulk-remove/",
            {"item_ids": [other_item_id]},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["deleted"], 0)

        # Original item still exists
        menu = self.get_menu(self.menu_id).json()
        self.assertEqual(len(menu["categories"][0]["items"]), 1)

    def test_bulk_update_categories_invalid_id(self):
        fake = "00000000-0000-0000-0000-000000000000"
        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/categories/bulk/",
            {"categories": [{"id": fake, "sort_order": 5}]},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_remove_empty_list_rejected(self):
        res = self.client.post(
            f"/api/v1/menus/{self.menu_id}/items/bulk-remove/",
            {"item_ids": []},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_update_categories_empty_list_rejected(self):
        res = self.client.patch(
            f"/api/v1/menus/{self.menu_id}/categories/bulk/",
            {"categories": []},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
