from django.urls import path
from electry_art.common.views import AcceptCookieNoticeView


urlpatterns = [
    path(
        "cookies/accept/", AcceptCookieNoticeView.as_view(), name="accept_cookie_notice",
    ),
]