from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView, PasswordChangeDoneView, \
    PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect

from django.urls import reverse_lazy
from django.views import generic, View
from django.views.generic import TemplateView
from django.db import transaction

from electry_art.user_profiles.forms import CreateProfileForm
from electry_art.user_profiles.signals import user_registered, _client_ip, _mask_email

import logging
audit_logger = logging.getLogger("electryart.audit")
logger = logging.getLogger("electryart.user_profiles")


UserModel = get_user_model()


class AccountLogin(LoginView):
    template_name = 'user_profile/account_login.html'


class AccountRegisterView(generic.CreateView):
    template_name = 'user_profile/account_create.html'
    form_class = CreateProfileForm
    success_url = reverse_lazy('index')

    def form_valid(self, form):
        result = super().form_valid(form)

        transaction.on_commit(
            lambda: (
                logger.info("User registered. user_id=%s", self.object.pk),
                audit_logger.info("REGISTER user_id=%s", self.object.pk),
                user_registered.send(sender=AccountRegisterView, user=self.object),
            )
        )

        login(self.request, self.object)
        return result


class AccountLogOut(LogoutView):
    next_page = reverse_lazy('index')


class AccountDetailsView(generic.DetailView):
    template_name = 'user_profile/account_details.html'
    model = UserModel


class AccountEditView(LoginRequiredMixin, generic.UpdateView):
    model = UserModel
    template_name = 'user_profile/account_edit.html'
    fields = ['username',
              'first_name',
              'last_name',
              'email',
              'country',
              'town',
              'address',
              'phone_num'
              ]

    def form_valid(self, form):
        response = super().form_valid(form)

        ip = _client_ip(self.request)
        actor_id = getattr(self.request.user, "pk", None)
        target_id = getattr(self.object, "pk", None)

        logger.info("Profile updated. actor_id=%s target_user_id=%s ip=%s", actor_id, target_id, ip)
        audit_logger.info("PROFILE_UPDATED actor_id=%s target_user_id=%s ip=%s", actor_id, target_id, ip)

        return response

    def get_success_url(self):
        return reverse_lazy('account details', kwargs={'pk': self.request.user.pk})


# class AccountDeleteView(generic.DeleteView):
#     template_name = 'user_profile/account_deactivate.html'
#     model = UserModel
#     success_url = reverse_lazy('index')


class AccountDeactivateView(LoginRequiredMixin, View):
    template_name = "user_profile/account_deactivate.html"
    success_url = reverse_lazy("index")

    def get(self, request, *args, **kwargs):
        # Confirm page
        return render(request, self.template_name)

    def post(self, request, *args, **kwargs):
        user = request.user

        # ако някога направиш деактивация по pk, тук ще сложим check actor/target.
        # засега: деактивира се само текущият user.
        if not user.is_authenticated:
            return HttpResponseForbidden()

        ip = _client_ip(request)

        # Deactivate
        user.is_active = False
        user.save(update_fields=["is_active"])

        # Log
        logger.info("Account deactivated. actor_id=%s target_user_id=%s ip=%s", user.pk, user.pk, ip)
        audit_logger.info("ACCOUNT_DEACTIVATED actor_id=%s target_user_id=%s ip=%s", user.pk, user.pk, ip)

        logout(request)

        return redirect(self.success_url)



class ChangeAccPasswordView(LoginRequiredMixin, PasswordChangeView):
    form_class = PasswordChangeForm
    template_name = "user_passwords/change_password.html"
    success_url = reverse_lazy("password_change_done")

    def form_valid(self, form):
        response = super().form_valid(form)

        ip = _client_ip(self.request)
        user_id = getattr(self.request.user, "pk", None)

        logger.info("Password changed. user_id=%s ip=%s", user_id, ip)
        audit_logger.info("PASSWORD_CHANGED user_id=%s ip=%s", user_id, ip)

        return response


class PassChanged(PasswordChangeDoneView):
    template_name = "user_passwords/change_pass_successful.html"


class PasswordReset(PasswordResetView):
    form_class = PasswordResetForm
    template_name = "user_passwords/password_reset.html"
    success_url = reverse_lazy("password_reset_done")

    def form_valid(self, form):
        email = form.cleaned_data.get("email")
        ip = _client_ip(self.request)
        email_mask = _mask_email(email)

        # 1) REQUESTED
        logger.info("Password reset requested. email=%s ip=%s", email_mask, ip)
        audit_logger.info("PASSWORD_RESET_REQUESTED email=%s ip=%s", email_mask, ip)

        # 2) Trying to send an email + SENT/FAILED
        try:
            form.save(
                request=self.request,
                use_https=self.request.is_secure(),
                token_generator=self.token_generator,
                from_email=self.from_email,
                email_template_name=self.email_template_name,
                subject_template_name=self.subject_template_name,
                html_email_template_name=self.html_email_template_name,
                extra_email_context=self.extra_email_context,
            )

            logger.info("Password reset email sent. email=%s ip=%s", email_mask, ip)
            audit_logger.info("PASSWORD_RESET_EMAIL_SENT email=%s ip=%s", email_mask, ip)

        except Exception:
            logger.exception("Password reset email failed. email=%s ip=%s", email_mask, ip)
            audit_logger.info("PASSWORD_RESET_EMAIL_FAILED email=%s ip=%s", email_mask, ip)

        return redirect(self.get_success_url())


class PasswordResetDone(PasswordResetDoneView):
    template_name = "user_passwords/password_reset_done.html"


class PasswordResetConfirm(PasswordResetConfirmView):
    form_class = SetPasswordForm
    template_name = "user_passwords/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")

    def form_valid(self, form):
        response = super().form_valid(form)

        ip = _client_ip(self.request)
        user_id = getattr(form.user, "pk", None)

        logger.info("Password reset completed. user_id=%s ip=%s", user_id, ip)
        audit_logger.info("PASSWORD_RESET_COMPLETED user_id=%s ip=%s", user_id, ip)

        return response


class PasswordResetComplete(PasswordResetCompleteView):
    template_name = "user_passwords/password_reset_complete.html"


class SuperuserPanelView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'user_profile/superuser_panel.html'

    def test_func(self):
        return self.request.user.is_superuser