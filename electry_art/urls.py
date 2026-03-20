"""
URL configuration for electry_art project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from electry_art.orders.views import StripeWebhookView

urlpatterns = [
    # URL for language change
    path("i18n/", include("django.conf.urls.i18n")),

    path("stripe/webhook/", StripeWebhookView.as_view(), name="stripe_webhook"),
]

urlpatterns += i18n_patterns(
    path('pitonq/', admin.site.urls),
    path('profile/', include('electry_art.user_profiles.urls')),
    path('', include('electry_art.products.urls')),
    path('cart/', include('electry_art.cart.urls')),
    path('orders/', include('electry_art.orders.urls')),
    path('site-support/', include('electry_art.site_support.urls')),
    path('', include('electry_art.common.urls'))
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)