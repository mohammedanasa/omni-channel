from django.test import TestCase
from integrations.adapters import AdapterRegistry
from integrations.adapters.base import AbstractChannelAdapter
from integrations.adapters.internal import InternalPOSAdapter


class TestAdapterRegistry(TestCase):

    def tearDown(self):
        AdapterRegistry.clear_cache()

    def test_get_adapter_class_valid(self):
        klass = AdapterRegistry.get_adapter_class(
            "integrations.adapters.internal.InternalPOSAdapter"
        )
        self.assertEqual(klass, InternalPOSAdapter)

    def test_get_adapter_class_cached(self):
        path = "integrations.adapters.internal.InternalPOSAdapter"
        klass1 = AdapterRegistry.get_adapter_class(path)
        klass2 = AdapterRegistry.get_adapter_class(path)
        self.assertIs(klass1, klass2)

    def test_get_adapter_class_invalid_path(self):
        with self.assertRaises((ImportError, AttributeError)):
            AdapterRegistry.get_adapter_class("nonexistent.module.Adapter")

    def test_get_adapter_class_not_subclass(self):
        with self.assertRaises(TypeError):
            AdapterRegistry.get_adapter_class("channels.models.Channel")

    def test_clear_cache(self):
        path = "integrations.adapters.internal.InternalPOSAdapter"
        AdapterRegistry.get_adapter_class(path)
        self.assertIn(path, AdapterRegistry._cache)
        AdapterRegistry.clear_cache()
        self.assertEqual(len(AdapterRegistry._cache), 0)
