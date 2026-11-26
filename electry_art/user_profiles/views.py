from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView, PasswordChangeDoneView, \
    PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.http import HttpResponseForbidden, HttpRequest
from django.shortcuts import render, redirect, get_object_or_404
from django import forms
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator

from django.urls import reverse_lazy
from django.views import generic, View
from django.views.generic import TemplateView
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from electry_art.cart.models import Cart

from electry_art.user_profiles.forms import CreateProfileForm, AddressForm
from electry_art.user_profiles.models import Address, UserProfile
from electry_art.user_profiles.signals import user_registered, _client_ip, _mask_email

import logging
import uuid

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


class AccountDetailsView(LoginRequiredMixin, generic.DetailView):
    template_name = 'user_profile/account_details.html'
    model = UserModel

    def get_object(self, queryset=None):
        return self.request.user


class AccountEditView(LoginRequiredMixin, generic.UpdateView):
    model = UserModel
    template_name = 'user_profile/account_edit.html'
    fields = ['username',
              'first_name',
              'last_name',
              'email',
              ]

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        response = super().form_valid(form)

        ip = _client_ip(self.request)
        actor_id = getattr(self.request.user, "pk", None)
        target_id = getattr(self.object, "pk", None)

        logger.info("Profile updated. actor_id=%s target_user_id=%s ip=%s", actor_id, target_id, ip)
        audit_logger.info("PROFILE_UPDATED actor_id=%s target_user_id=%s ip=%s", actor_id, target_id, ip)

        return response

    def get_success_url(self):
        return reverse_lazy('account_details')


class AccountDeactivateView(LoginRequiredMixin, View):
    template_name = "user_profile/account_deactivate.html"
    success_url = reverse_lazy("index")

    def get(self, request, *args, **kwargs):
        # Confirm page
        return render(request, self.template_name)

    def post(self, request, *args, **kwargs):
        user = request.user

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


class AccountRecoveryAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    request: HttpRequest

    def test_func(self) -> bool:
        user = self.request.user
        return bool(user.is_active and ( user.is_staff or user.is_superuser))

    def recovery_queryset(self) -> QuerySet:
        qs = UserProfile.objects.all()

        if not self.request.user.is_superuser:
            qs = qs.filter(is_staff=False,is_superuser=False,)
        return qs

    @staticmethod
    def can_restore(user: UserProfile) -> bool:
        return (
            not user.is_active
            and user.deleted_at is None
            and user.has_usable_password()
            and not user.email.lower().endswith(
                '@deleted.invalid'
            )
        )


class UserEmailSearchForm(forms.Form):
    email = forms.EmailField(max_length=254)


@method_decorator(never_cache, name='dispatch')
class UserEmailSearchView(AccountRecoveryAccessMixin, View):
    template_name = 'user_profile/user_search_results.html'

    def get(self, request):
        return render(request, self.template_name, {'form': UserEmailSearchForm()})

    def post(self, request):
        form = UserEmailSearchForm(request.POST)
        results = []
        if form.is_valid():
            users = self.recovery_queryset().filter(email__iexact=form.cleaned_data['email']).order_by('pk')
            results = [{'account': user, 'can_restore': self.can_restore(user)} for user in users]
        return render(request, self.template_name, {'form': form, 'results': results, 'searched': form.is_valid()})


@method_decorator(never_cache, name='dispatch')
class AccountRestoreView(AccountRecoveryAccessMixin, View):
    template_name = 'user_profile/account_restore.html'

    def get(self, request, pk):
        account = get_object_or_404(self.recovery_queryset(), pk=pk)
        if not self.can_restore(account):
            return HttpResponseForbidden('Account cannot be restored.')
        return render(request, self.template_name, {'account': account})

    def post(self, request, pk):
        with transaction.atomic():
            account = get_object_or_404(self.recovery_queryset().select_for_update(), pk=pk)
            if not self.can_restore(account):
                return HttpResponseForbidden('Account cannot be restored.')
            account.is_active = True
            account.save(update_fields=['is_active'])
            actor_id, target_id, ip = request.user.pk, account.pk, _client_ip(request)
            transaction.on_commit(lambda: audit_logger.info(
                'ACCOUNT_RESTORED actor_id=%s target_user_id=%s ip=%s', actor_id, target_id, ip))
        return render(request, self.template_name, {'account': account, 'restored': True})


class AccountDeleteForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}), strip=False)
    confirm = forms.BooleanField(label='I understand that this action cannot be undone.')


@method_decorator(never_cache, name='dispatch')
class AccountDeleteView(LoginRequiredMixin, View):
    template_name = 'user_profile/account_delete.html'
    success_url = reverse_lazy('index')

    def get(self, request):
        if request.user.is_staff or request.user.is_superuser:
            return HttpResponseForbidden('Privileged accounts cannot be deleted here.')
        return render(request, self.template_name, {'form': AccountDeleteForm()})

    def post(self, request):
        form = AccountDeleteForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})
        with transaction.atomic():
            user = UserProfile.objects.select_for_update().get(pk=request.user.pk)
            if not user.is_active or user.deleted_at is not None or user.is_staff or user.is_superuser:
                return HttpResponseForbidden('Account cannot be deleted here.')
            if not user.check_password(form.cleaned_data['password']):
                form.add_error('password', 'Incorrect password.')
                return render(request, self.template_name, {'form': form})

            # Random suffix avoids collisions with ordinary registered usernames.
            while True:
                token = uuid.uuid4().hex[:24]
                username = f'deleted_{token}'
                email = f'{username}@deleted.invalid'
                if not UserProfile.objects.filter(username__iexact=username).exists() and not UserProfile.objects.filter(email__iexact=email).exists():
                    break
            user.username = username
            user.email = email
            user.first_name = None
            user.last_name = None
            user.is_active = False
            user.is_staff = False
            user.is_superuser = False
            user.deleted_at = timezone.now()
            user.set_unusable_password()
            user.save(update_fields=['username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_superuser', 'deleted_at', 'password'])
            user.groups.clear()
            user.user_permissions.clear()
            Address.objects.filter(user=user).delete()
            Cart.objects.filter(user=user).delete()
            actor_id = user.pk
            transaction.on_commit(lambda: audit_logger.info('ACCOUNT_DELETED actor_id=%s', actor_id))
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


class AddressCreateView(LoginRequiredMixin, generic.CreateView):
    model = Address
    form_class = AddressForm
    template_name = 'user_profile/address_create.html'
    success_url = reverse_lazy('account_details')

    def form_valid(self, form):
        # Lock the owner row: serialize changes to defaults for this user.
        with transaction.atomic():
            UserModel.objects.select_for_update().get(pk=self.request.user.pk)
            form.instance.user = self.request.user
            existing = Address.objects.filter(user=self.request.user)
            # First-ever address is always default; later ones are opt-in.
            form.instance.is_default = not existing.exists() or form.cleaned_data['is_default']
            if form.instance.is_default:
                existing.filter(is_default=True).update(is_default=False)
            return super().form_valid(form)


class AddressUpdateView(LoginRequiredMixin, generic.UpdateView):
    model = Address
    form_class = AddressForm
    template_name = 'user_profile/address_edit.html'
    success_url = reverse_lazy('account_details')

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def form_valid(self, form):
        with transaction.atomic():
            UserModel.objects.select_for_update().get(pk=self.request.user.pk)
            # Re-fetch the object under the lock to avoid stale updates.
            current = Address.objects.get(pk=self.object.pk, user=self.request.user)
            if form.cleaned_data['is_default']:
                Address.objects.filter(user=self.request.user, is_default=True).exclude(
                    pk=current.pk
                ).update(is_default=False)
            form.instance.user = self.request.user
            return super().form_valid(form)


class AddressDeleteView(LoginRequiredMixin, generic.DeleteView):
    model = Address
    template_name = 'user_profile/address_delete.html'
    success_url = reverse_lazy('account_details')

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)



