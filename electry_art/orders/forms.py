from django import forms


class BaseCheckoutForm(forms.Form):
    full_name = forms.CharField(max_length=100, min_length=3)
    phone = forms.CharField(max_length=20)
    address = forms.CharField(widget=forms.Textarea(attrs={
        'placeholder': 'Enter your delivery address',
    }))

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        allowed = "+0123456789 "
        if any(ch not in allowed for ch in phone):
            raise forms.ValidationError("Invalid phone number format")
        return phone


class CheckoutForm(BaseCheckoutForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and getattr(user, "is_authenticated", False):
            self.fields["full_name"].initial = (user.get_name or "").strip()
            self.fields["phone"].initial = user.phone_num or ""
            self.fields["address"].initial = user.get_full_address or ""


class GuestCheckoutForm(BaseCheckoutForm):
    email = forms.EmailField()


