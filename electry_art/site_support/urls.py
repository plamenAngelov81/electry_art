from django.urls import path, include

from electry_art.site_support.views import SupportSiteIndexView, TermsOfUseView, DeliveryView, ReturnsView, PrivacyView, \
    InquiryCreateView, InquiryListView, InquiryDetailView

urlpatterns = [
    path('', include([
        path('', SupportSiteIndexView.as_view(), name='site-support-index'),
        path('terms/', TermsOfUseView.as_view(), name='terms'),
        path('delivery/', DeliveryView.as_view(), name='delivery'),
        path('returns/', ReturnsView.as_view(), name='returns'),
        path('privacy/', PrivacyView.as_view(), name='privacy'),

        path('inquiry/', include([
        path('', InquiryCreateView.as_view(), name='inquiry'),
        path('inquiry-list/', InquiryListView.as_view(), name='inquiry-list'),
        path('inquiries/<int:pk>/', InquiryDetailView.as_view(), name='inquiry-detail'),
        ])),
    ]))
]
