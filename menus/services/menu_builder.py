from django.db import transaction

from menus.models import (
    Menu,
    MenuCategory,
    MenuItem,
    MenuLocation,
    MenuLocationChannel,
)


class MenuBuilderService:

    @staticmethod
    @transaction.atomic
    def duplicate_menu(menu, new_name=None):
        """Create a full copy of a menu (categories, items). Locations are NOT copied."""
        new_menu = Menu.objects.create(
            name=new_name or f"{menu.name} (Copy)",
            description=menu.description,
            image_url=menu.image_url,
            is_active=False,
            sort_order=menu.sort_order,
        )

        for cat in menu.categories.all():
            new_cat = MenuCategory.objects.create(
                menu=new_menu,
                name=cat.name,
                description=cat.description,
                image_url=cat.image_url,
                sort_order=cat.sort_order,
            )
            items = []
            for item in cat.items.all():
                items.append(
                    MenuItem(
                        menu_category=new_cat,
                        product=item.product,
                        sort_order=item.sort_order,
                        price_override=item.price_override,
                        is_visible=item.is_visible,
                    )
                )
            MenuItem.objects.bulk_create(items)

        for avail in menu.availabilities.all():
            avail.pk = None
            avail.menu = new_menu
            avail.save()

        return new_menu

    @staticmethod
    @transaction.atomic
    def bulk_update_items(menu, updates):
        """
        Bulk update menu items.
        updates: list of dicts, each with 'id' and fields to update.
        Allowed fields: sort_order, price_override, is_visible, menu_category.
        Returns: list of updated MenuItem instances.
        """
        allowed_fields = {"sort_order", "price_override", "is_visible", "menu_category"}
        item_ids = [u["id"] for u in updates]
        items = {
            str(item.id): item
            for item in MenuItem.objects.filter(
                id__in=item_ids, menu_category__menu=menu
            )
        }

        not_found = [u["id"] for u in updates if str(u["id"]) not in items]
        if not_found:
            raise ValueError(f"Items not found in this menu: {not_found}")

        fields_to_update = set()
        for update in updates:
            item = items[str(update["id"])]
            for field, value in update.items():
                if field == "id":
                    continue
                if field not in allowed_fields:
                    raise ValueError(f"Field '{field}' is not allowed.")
                if field == "menu_category":
                    cat = MenuCategory.objects.filter(id=value, menu=menu).first()
                    if not cat:
                        raise ValueError(f"Category '{value}' not found in this menu.")
                    item.menu_category = cat
                else:
                    setattr(item, field, value)
                fields_to_update.add(field if field != "menu_category" else "menu_category_id")

        if fields_to_update:
            MenuItem.objects.bulk_update(list(items.values()), list(fields_to_update))

        return list(items.values())

    @staticmethod
    @transaction.atomic
    def bulk_update_categories(menu, updates):
        """
        Bulk update menu categories.
        updates: list of dicts, each with 'id' and fields to update.
        Allowed fields: sort_order, name, description, image_url.
        Returns: list of updated MenuCategory instances.
        """
        allowed_fields = {"sort_order", "name", "description", "image_url"}
        cat_ids = [u["id"] for u in updates]
        categories = {
            str(cat.id): cat
            for cat in MenuCategory.objects.filter(id__in=cat_ids, menu=menu)
        }

        not_found = [u["id"] for u in updates if str(u["id"]) not in categories]
        if not_found:
            raise ValueError(f"Categories not found in this menu: {not_found}")

        fields_to_update = set()
        for update in updates:
            cat = categories[str(update["id"])]
            for field, value in update.items():
                if field == "id":
                    continue
                if field not in allowed_fields:
                    raise ValueError(f"Field '{field}' is not allowed.")
                setattr(cat, field, value)
                fields_to_update.add(field)

        if fields_to_update:
            MenuCategory.objects.bulk_update(list(categories.values()), list(fields_to_update))

        return list(categories.values())

    @staticmethod
    @transaction.atomic
    def bulk_remove_items(menu, item_ids):
        """
        Bulk remove items from a menu.
        Returns: count of deleted items.
        """
        deleted, _ = MenuItem.objects.filter(
            id__in=item_ids, menu_category__menu=menu
        ).delete()
        return deleted

    @staticmethod
    @transaction.atomic
    def assign_locations(menu, location_ids):
        """Assign a menu to multiple locations at once. Skips existing."""
        created = []
        for loc_id in location_ids:
            ml, was_created = MenuLocation.objects.get_or_create(
                menu=menu, location_id=loc_id
            )
            if was_created:
                created.append(ml)
        return created

    @staticmethod
    @transaction.atomic
    def assign_channels(menu_location, channel_link_ids):
        """Assign channel links to a menu-location. Skips existing."""
        created = []
        for cl_id in channel_link_ids:
            mlc, was_created = MenuLocationChannel.objects.get_or_create(
                menu_location=menu_location, channel_link_id=cl_id
            )
            if was_created:
                created.append(mlc)
        return created
