from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, UsernameField
from django import forms
from electry_art.user_profiles.models import Address

UserModel = get_user_model()


class CreateProfileForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'placeholder': 'Enter email',
        })
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Enter password',
        })
    )

    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Confirm password',
        })
    )

    class Meta:
        model = UserModel
        fields = ['username', 'email', 'first_name', 'last_name']
        field_classes = {
            'username': UsernameField
        }
        widgets = {
            'username': forms.TextInput(attrs={
                'placeholder': 'Enter username',
            }),
            'first_name': forms.TextInput(attrs={
                'placeholder': 'Enter first name',
            }),
            'last_name': forms.TextInput(attrs={
                'placeholder': 'Enter last name',
            }),
        }


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = (
            'country', 'town', 'address', 'phone_num',
            'courier_company', 'courier_office', 'is_default',
        )
