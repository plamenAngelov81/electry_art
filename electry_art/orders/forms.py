from django import forms


class BaseCheckoutForm(forms.Form):
    full_name = forms.CharField(max_length=100, min_length=3)
    phone = forms.CharField(max_length=20)

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        allowed = "+0123456789 "
        if any(ch not in allowed for ch in phone):
            raise forms.ValidationError("Invalid phone number format")
        return phone


class CheckoutForm(forms.Form):
    delivery_address = forms.ModelChoiceField(
        queryset=None,
        empty_label="Select delivery address",
        label="Delivery Address",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        if user and getattr(user, "is_authenticated", False):
            self.fields["delivery_address"].queryset = user.addresses.all()


class GuestCheckoutForm(BaseCheckoutForm):
    email = forms.EmailField(max_length=254)
    address = forms.CharField(widget=forms.Textarea(attrs={
        'placeholder': 'Enter your delivery address',
    }))