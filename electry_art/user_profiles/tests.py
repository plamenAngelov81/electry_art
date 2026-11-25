"""Regression tests for audit issue #26: custom user Django admin."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from urllib.parse import parse_qs, urlsplit
from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import override
from django.db import IntegrityError, transaction

from electry_art.user_profiles.models import Address

User = get_user_model()

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


class UserProfileAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username="issue26admin",
            email="issue26admin@example.com",
            password="AdminTestPassword_26!",
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_custom_user_is_registered_with_user_admin(self):
        self.assertIn(User, admin.site._registry)
        self.assertIsInstance(admin.site._registry[User], UserAdmin)

    def test_admin_add_user_hashes_password(self):
        url = reverse(f"admin:{User._meta.app_label}_{User._meta.model_name}_add")
        response = self.client.post(url, {
            "username": "issue26newuser",
            "password1": "NewTestPassword_26!",
            "password2": "NewTestPassword_26!",
            "usable_password": "true",
            "_save": "Save",
        })
        if response.status_code != 302:
            self.fail(
                f"Admin add returned HTTP {response.status_code}; "
                f"form errors: {getattr(response.context.get('adminform', None), 'form', None).errors if response.context and response.context.get('adminform') else 'not available'}"
            )
        created = User.objects.get(username="issue26newuser")
        self.assertNotEqual(created.password, "NewTestPassword_26!")
        self.assertTrue(created.check_password("NewTestPassword_26!"))

    def test_admin_password_change_hashes_new_password(self):
        target = User.objects.create_user(
            username="issue26target",
            email="issue26target@example.com",
            password="OriginalTestPassword_26!",
        )

        old_hash = target.password

        change_url = reverse(
            f"admin:{User._meta.app_label}_{User._meta.model_name}_change",
            args=[target.pk],
        )

        url = change_url.replace(
            "/change/",
            "/password/",
        )

        response = self.client.post(url,{"password1": "UpdatedTestPassword_26!","password2": "UpdatedTestPassword_26!",},)

        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertNotEqual(target.password, old_hash)
        self.assertTrue(target.check_password("UpdatedTestPassword_26!"))
        self.assertFalse(target.check_password("OriginalTestPassword_26!"))

    def test_admin_change_page_does_not_expose_raw_password_editor(self):
        target = User.objects.create_user(
            username="issue26existing",
            email="issue26existing@example.com",
            password="ExistingTestPassword_26!",
        )
        url = reverse(
            f"admin:{User._meta.app_label}_{User._meta.model_name}_change",
            args=[target.pk],
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        admin_form = response.context["adminform"].form
        self.assertIn("password", admin_form.fields)
        self.assertIsInstance(
            admin_form.fields["password"], ReadOnlyPasswordHashField
        )
        target.refresh_from_db()
        self.assertTrue(target.check_password("ExistingTestPassword_26!"))


class AddressIssue27Tests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='address27', email='address27@example.com', password='TestPassword27!'
        )
        self.client.force_login(self.user)
        self.payload = {
            'country': 'Bulgaria', 'town': 'Gabrovo',
            'address': 'Example Street 10', 'phone_num': '0888123456',
            'courier_company': '', 'courier_office': '',
        }

    def add(self, **overrides):
        return self.client.post(reverse('address_add'), {**self.payload, **overrides})

    def test_first_address_becomes_default_even_without_checkbox(self):
        self.assertEqual(self.add().status_code, 302)
        self.assertTrue(Address.objects.get(user=self.user).is_default)

    def test_later_address_does_not_change_default(self):
        self.add()
        first = Address.objects.get(user=self.user)
        self.add(address='Another Street 20')
        self.assertEqual(Address.objects.filter(user=self.user).count(), 2)
        self.assertEqual(list(Address.objects.filter(user=self.user, is_default=True)
                              .values_list('pk', flat=True)), [first.pk])

    def test_selecting_new_default_unsets_old(self):
        self.add()
        self.add(address='Another Street 20', is_default='on')
        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)
        self.assertEqual(Address.objects.get(user=self.user, is_default=True).address,
                         'Another Street 20')

    def test_deleting_default_does_not_promote_other(self):
        self.add()
        first = Address.objects.get(user=self.user)
        self.add(address='Another Street 20')
        self.assertEqual(self.client.post(reverse('address delete', args=[first.pk])).status_code, 302)
        self.assertEqual(Address.objects.filter(user=self.user).count(), 1)
        self.assertFalse(Address.objects.filter(user=self.user, is_default=True).exists())

    def test_missing_delivery_destination_is_rejected(self):
        response = self.add(address='', courier_company='', courier_office='')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Address.objects.filter(user=self.user).exists())

    def test_courier_office_is_accepted(self):
        self.assertEqual(self.add(address='', courier_company='Econt',
                                  courier_office='Gabrovo Center').status_code, 302)
        self.assertEqual(Address.objects.filter(user=self.user).count(), 1)

    def test_incomplete_courier_pair_is_rejected(self):
        response = self.add(address='', courier_company='Econt', courier_office='')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Address.objects.filter(user=self.user).count(), 0)

    def test_database_rejects_two_defaults(self):
        Address.objects.create(user=self.user, is_default=True, **self.payload)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Address.objects.create(user=self.user, is_default=True,
                                       **{**self.payload, 'address': 'Another Street 20'})


class AccountRestoreIssue28Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(username='staff28', email='staff28@example.com', password='Password28!', is_staff=True)
        cls.admin = User.objects.create_superuser(username='admin28', email='admin28@example.com', password='Password28!')
        cls.customer = User.objects.create_user(username='customer28', email='customer28@example.com', password='Password28!', is_active=False)
        cls.other = User.objects.create_user(username='other28', email='other28@example.com', password='Password28!')

    def setUp(self):
        self.search = reverse('user_email_search')
        self.restore = reverse('account_restore', args=[self.customer.pk])

    def test_staff_search_exact_case_insensitive(self):
        self.client.force_login(self.staff)
        response = self.client.post(self.search, {'email': 'CUSTOMER28@example.com'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r['account'].pk for r in response.context['results']], [self.customer.pk])

    def test_anonymous_denied(self):
        self.assertEqual(self.client.post(self.search, {'email': self.customer.email}).status_code, 302)
        self.assertEqual(self.client.post(self.restore).status_code, 302)

    def test_customer_denied(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.search, {'email': self.customer.email}).status_code, 403)
        self.assertEqual(self.client.post(self.restore).status_code, 403)

    def test_get_does_not_restore(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.restore).status_code, 200)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)

    def test_staff_restores_preserving_data(self):
        self.client.force_login(self.staff)
        old = self.customer.password
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(self.restore).status_code, 200)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)
        self.assertEqual(self.customer.password, old)
        self.assertEqual(self.customer.email, 'customer28@example.com')
        self.assertTrue(self.customer.check_password('Password28!'))

    def test_superuser_restores(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.restore).status_code, 200)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)

    def test_staff_cannot_restore_privileged_account(self):
        self.customer.is_staff = True
        self.customer.save(update_fields=['is_staff'])
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(self.restore).status_code, 404)

    def test_unusable_password_blocks_restore(self):
        self.customer.set_unusable_password()
        self.customer.save(update_fields=['password'])
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.restore).status_code, 403)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)

    def test_active_account_cannot_be_restored(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('account_restore', args=[self.other.pk])).status_code, 403)

    def test_csrf_required(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        self.assertEqual(client.post(self.restore).status_code, 403)
