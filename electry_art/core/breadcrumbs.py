from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class Breadcrumbs:
    """Helper class for building breadcrumb navigation."""

    @staticmethod
    def item(title, url=""):
        """
        Create a custom breadcrumb item.

        Example:
            Breadcrumbs.item(product.name)
            Breadcrumbs.item(_("Edit"), reverse("product edit", kwargs={"pk": 1}))
        """
        return {
            "title": title,
            "url": url,
        }

    @staticmethod
    def home():
        """Home page."""
        return Breadcrumbs.item(
            _("Home"),
            reverse("index"),
        )

    @staticmethod
    def products():
        """Products list."""
        return Breadcrumbs.item(
            _("Products"),
            reverse("product list"),
        )

    @staticmethod
    def wishlist():
        """Wishlist page."""
        return Breadcrumbs.item(
            _("Wishlist"),
            reverse("wishlist"),
        )

    @staticmethod
    def search():
        """Search results."""
        return Breadcrumbs.item(
            _("Search"),
        )

    @staticmethod
    def products_path():
        return [
            Breadcrumbs.home(),
            Breadcrumbs.products(),
        ]

    @staticmethod
    def support():
        return Breadcrumbs.item(
            _("Support Center"),
            reverse("site-support-index"),
        )

    @staticmethod
    def terms():
        return Breadcrumbs.item(_("Terms"))

    @staticmethod
    def delivery():
        return Breadcrumbs.item(_("Delivery"))

    @staticmethod
    def returns():
        return Breadcrumbs.item(_("Returns"))

    @staticmethod
    def privacy():
        return Breadcrumbs.item(_("Privacy"))

    @staticmethod
    def cookie_policy():
        return Breadcrumbs.item(_("Cookies"))

    @staticmethod
    def site_support_path():
        return [
            Breadcrumbs.home(),
            Breadcrumbs.support(),
        ]

    @staticmethod
    def inquiry():
        return Breadcrumbs.item((_('Inquiry')))

    @staticmethod
    def inquiry_create():
        return Breadcrumbs.item((_('Inquiry create')))

    @staticmethod
    def inquiry_details():
        return Breadcrumbs.item((_('Inquiry Details')))