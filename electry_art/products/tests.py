
"""Regression tests for issue #25: property creation redirects."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from electry_art.products.models import ProductColor, ProductMaterial, ProductType


class ProductPropertyCreationRedirectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username="issue25_admin", email="issue25@example.com", password="test-pass-25"
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_type_creation_saves_and_redirects(self):
        response = self.client.post(reverse("type create"), {"name": "Test type 25", "name_en": "Test Type 25", "name_bg": "Тестов тип 25"})
        self.assertRedirects(response, reverse("superuser_panel"), fetch_redirect_response=False)
        self.assertEqual(ProductType.objects.filter(name_en="Test Type 25").count(), 1)

    def test_material_creation_saves_and_redirects(self):
        response = self.client.post(reverse("material create"), {"name": "Test Material 25", "name_en": "Test Material 25", "name_bg": "Тестов материал 25"})
        self.assertRedirects(response, reverse("superuser_panel"), fetch_redirect_response=False)
        self.assertEqual(ProductMaterial.objects.filter(name_en="Test Material 25").count(), 1)

    def test_color_creation_saves_and_redirects(self):
        response = self.client.post(reverse("color create"), {"name": "Test color 25", "name_en": "Test Color 25", "name_bg": "Тестов цвят 25"})
        self.assertRedirects(response, reverse("superuser_panel"), fetch_redirect_response=False)
        self.assertEqual(ProductColor.objects.filter(name_en="Test Color 25").count(), 1)
