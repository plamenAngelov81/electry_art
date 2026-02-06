from django.urls import path, include

from electry_art.user_profiles.views import AccountRegisterView, AccountLogin, AccountLogOut, AccountDetailsView, \
    AccountEditView, ChangeAccPasswordView, PassChanged, PasswordResetDone, PasswordReset, \
    PasswordResetConfirm, PasswordResetComplete, SuperuserPanelView, AccountDeactivateView

urlpatterns = [
    path('', include([
        path('superuser-panel/', SuperuserPanelView.as_view(), name='superuser panel'),
        path('register/', AccountRegisterView.as_view(), name='account register'),
        path('login/', AccountLogin.as_view(), name='account login'),
        path('logout/', AccountLogOut.as_view(), name='account logout'),
        path('<int:pk>/', AccountDetailsView.as_view(), name='account details'),
        path('edit/<int:pk>/', AccountEditView.as_view(), name='account edit'),
        path('deactivate/<int:pk>/', AccountDeactivateView.as_view(), name='account deactivate'),

        path('<int:pk>/change-password', ChangeAccPasswordView.as_view(), name='change password'),
        path('pass-changed/', PassChanged.as_view(), name='password_change_done'),

        path('pass-reset/', PasswordReset.as_view(), name='reset_password'),
        path('pass-reset-send/', PasswordResetDone.as_view(), name='password_reset_done'),
        path('reset/<uidb64>/<token>/', PasswordResetConfirm.as_view(), name='password_reset_confirm'),
        path('pass-reset-complete/', PasswordResetComplete.as_view(), name='password_reset_complete'),
    ])),
]