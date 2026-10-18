from importlib import import_module

from django.test import SimpleTestCase
from django.urls import resolve, reverse


class RootUrlconfTests(SimpleTestCase):
    def test_docs_url_resolves(self):
        match = resolve("/api/docs")
        self.assertEqual(match.view_name, "api-1.0.0:openapi-view")

    def test_openapi_url_resolves(self):
        match = resolve("/api/openapi.json")
        self.assertEqual(match.view_name, "api-1.0.0:openapi-json")

    def test_api_namespace_is_reverseable(self):
        self.assertEqual(reverse("api-1.0.0:openapi-json"), "/api/openapi.json")
        self.assertEqual(reverse("api-1.0.0:openapi-view"), "/api/docs")

    def test_api_mounted_before_dashboard_include(self):
        urlpatterns = import_module("ifcbdb.urls").urlpatterns
        patterns = [str(p.pattern) for p in urlpatterns]
        self.assertLess(patterns.index("api/"), patterns.index(""))
