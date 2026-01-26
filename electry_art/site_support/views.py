
from electry_art.orders.forms import InquiryForm
from electry_art.orders.models import Inquiry
from django.urls import reverse_lazy
from django.views import generic
from electry_art.products.product_mixins.product_mixins import SuperuserRequiredMixin


class SupportSiteIndexView(generic.TemplateView):
    template_name = 'site_support/site_support_index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

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
        ]

        return context



class TermsOfUseView(generic.TemplateView):
    template_name = 'site_support/terms.html'


class DeliveryView(generic.TemplateView):
    template_name = 'site_support/delivery.html'


class ReturnsView(generic.TemplateView):
    template_name = 'site_support/returns.html'


class PrivacyView(generic.TemplateView):
    template_name = 'site_support/privacy.html'


class InquiryCreateView(generic.CreateView):
    model = Inquiry
    form_class = InquiryForm
    template_name = 'site_support/inquiry_form.html'
    success_url = reverse_lazy('index')


class InquiryListView(SuperuserRequiredMixin, generic.ListView):
    model = Inquiry
    template_name = 'site_support/inquiry_list.html'

    def get_queryset(self):
        return Inquiry.objects.all().order_by('-created_at')


class InquiryDetailView(SuperuserRequiredMixin, generic.DetailView):
    model = Inquiry
    template_name = 'site_support/inquiry_detail.html'
    context_object_name = 'inquiry'