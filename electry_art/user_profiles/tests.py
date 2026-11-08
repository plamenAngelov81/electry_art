
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import override


class LoginRedirectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="login_redirect_test_user",
            email="login_redirect_test_user@example.com",
            password="TestPassword_2026!",
        )

    def test_login_url_setting_points_to_registered_route(self):
        self.assertEqual(str(settings.LOGIN_URL), reverse("account_login"))

    def test_anonymous_protected_view_redirects_to_login_with_next(self):
        target = reverse("account_details")
        response = self.client.get(target)
        self.assertEqual(response.status_code, 302)
        location = urlsplit(response["Location"])
        self.assertEqual(location.path, reverse("account_login"))
        self.assertEqual(parse_qs(location.query).get("next"), [target])

    def test_login_template_preserves_next_on_post(self):
        target = reverse("account_details")
        response = self.client.get(reverse("account_login"), {"next": target})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="next"')
        self.assertContains(response, f'value="{target}"')

    def test_successful_login_returns_to_original_page(self):
        target = reverse("account_details")
        response = self.client.post(reverse("account_login"), {
            "username": self.user.username,
            "password": "TestPassword_2026!",
            "next": target,
        })
        self.assertRedirects(response, target, fetch_redirect_response=False)

    def test_external_next_is_rejected(self):
        response = self.client.post(reverse("account_login"), {
            "username": self.user.username,
            "password": "TestPassword_2026!",
            "next": "https://attacker.example/steal",
        })
        self.assertRedirects(response, reverse("index"), fetch_redirect_response=False)

    def test_login_without_next_uses_default_redirect(self):
        response = self.client.post(reverse("account_login"), {
            "username": self.user.username,
            "password": "TestPassword_2026!",
        })
        self.assertRedirects(response, reverse("index"), fetch_redirect_response=False)

    def test_language_aware_login_urls(self):
        for language in ("en", "bg"):
            with self.subTest(language=language), override(language):
                target = reverse("account_details")
                login_url = reverse("account_login")
                self.assertTrue(login_url.startswith(f"/{language}/"))
                response = self.client.get(target)
                self.assertEqual(response.status_code, 302)
                location = urlsplit(response["Location"])
                self.assertEqual(location.path, login_url)
                self.assertEqual(parse_qs(location.query).get("next"), [target])
