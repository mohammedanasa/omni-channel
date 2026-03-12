from django.contrib import admin
from .models import Menu, MenuCategory, MenuItem, MenuAvailability, MenuLocation, MenuLocationChannel

admin.site.register(Menu)
admin.site.register(MenuCategory)
admin.site.register(MenuItem)
admin.site.register(MenuAvailability)
admin.site.register(MenuLocation)
admin.site.register(MenuLocationChannel)
