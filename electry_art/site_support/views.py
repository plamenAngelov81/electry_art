from electry_art.core.breadcrumbs import Breadcrumbs
from electry_art.site_support.forms import InquiryForm
from electry_art.site_support.models import Inquiry
from django.urls import reverse_lazy
from django.views import generic
from electry_art.products.product_mixins.product_mixins import SuperuserRequiredMixin
from django.utils.translation import gettext_lazy as _


class SupportSiteIndexView(generic.TemplateView):
    template_name = 'site_support/site_support_index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["breadcrumbs"] = [
            Breadcrumbs.home(),
            Breadcrumbs.item(_("Support Center")),
        ]

        context['support_links'] = [
            {
                'title': 'Terms of Use',
                'description': 'Rules for using ElectryArt.',
                'url': reverse_lazy('terms'),
            },
            {
                'title': 'Delivery',
                'description': 'Shipping methods, costs, and delivery times.',
                'url': reverse_lazy('delivery'),
            },
            {
                'title': 'Returns',
                'description': 'How to return an order and get a refund.',
                'url': reverse_lazy('returns'),
            },
            {
                'title': 'Privacy',
                'description': 'How we handle and protect your personal data.',
                'url': reverse_lazy('privacy'),
            },
            {
                'title': 'Inquiry',
                'description': 'Contact us if you have questions or need support.',
                'url': reverse_lazy('inquiry'),
            },
            {
                'title': 'Cookies',
                'description': 'Cookie Policy.',
                'url': reverse_lazy('cookie_policy'),
            },
        ]

        return context



class TermsOfUseView(generic.TemplateView):
    template_name = 'site_support/terms.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = Breadcrumbs.site_support_path() + [Breadcrumbs.item(_("Terms of Use")),]
        return context


class DeliveryView(generic.TemplateView):
    template_name = 'site_support/delivery.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = Breadcrumbs.site_support_path() + [Breadcrumbs.item(_("Delivery")),]
        return context


class ReturnsView(generic.TemplateView):
    template_name = 'site_support/returns.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = Breadcrumbs.site_support_path() + [Breadcrumbs.item(_("Returns")),]
        return context


class PrivacyView(generic.TemplateView):
    template_name = 'site_support/privacy.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = Breadcrumbs.site_support_path() + [Breadcrumbs.item(_("Privacy")),]
        return context


class CookiePrivacyView(generic.TemplateView):
    template_name = 'site_support/cookie_policy.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = Breadcrumbs.site_support_path() + [Breadcrumbs.item(_("Cookies")),]
        return context


class InquiryCreateView(generic.CreateView):
    model = Inquiry
    form_class = InquiryForm
    template_name = 'site_support/inquiry_form.html'
    success_url = reverse_lazy('index')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = Breadcrumbs.site_support_path() + [Breadcrumbs.item(_("Inquiry Create")),]
        return context


class InquiryListView(SuperuserRequiredMixin, generic.ListView):
    model = Inquiry
    template_name = 'site_support/inquiry_list.html'

    def get_queryset(self):
        return Inquiry.objects.all().order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = Breadcrumbs.site_support_path() + [Breadcrumbs.item(_("Inquiry List")),]
        return context


class InquiryDetailView(SuperuserRequiredMixin, generic.DetailView):
    model = Inquiry
    template_name = 'site_support/inquiry_detail.html'
    context_object_name = 'inquiry'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = Breadcrumbs.site_support_path() + [Breadcrumbs.item(_("Inquiry Details")),]
        return context