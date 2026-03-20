
from django.conf import settings
from django.http import HttpResponseRedirect
from django.views import View


class AcceptCookieNoticeView(View):
    @staticmethod
    def post(request, *args, **kwargs):
        redirect_to = request.META.get("HTTP_REFERER", "/")
        response = HttpResponseRedirect(redirect_to)

        response.set_cookie(
            key=getattr(settings, "COOKIE_NOTICE_NAME", "electryart_cookie_notice_accepted"),
            value="1",
            max_age=getattr(settings, "COOKIE_NOTICE_AGE", 60 * 60 * 24 * 365),
            secure=not settings.DEBUG,
            httponly=True,
            samesite="Lax",
        )
        return response
