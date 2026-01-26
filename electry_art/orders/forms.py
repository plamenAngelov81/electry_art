from django import forms

from electry_art.orders.models import Inquiry


class CheckoutForm(forms.Form):
    full_name = forms.CharField(max_length=100)
    phone = forms.CharField(max_length=20)
    address = forms.CharField(widget=forms.Textarea)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        if user and getattr(user, "is_authenticated", False):
            self.fields["full_name"].initial = (user.get_name or "").strip()
            self.fields["phone"].initial = user.phone_num or ""
            full_addr = user.get_full_address
            self.fields["address"].initial = full_addr or ""

    def clean_phone(self):
        phone = self.cleaned_data['phone']
        allowed = "+0123456789 "
        if any(ch not in allowed for ch in phone):
            raise forms.ValidationError("Invalid phone number format")
        return phone


class GuestCheckoutForm(forms.Form):
    full_name = forms.CharField(max_length=100)
    email = forms.EmailField()
    phone = forms.CharField(max_length=20)
    address = forms.CharField(widget=forms.Textarea)

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        allowed = "+0123456789 "
        if any(ch not in allowed for ch in phone):
            raise forms.ValidationError("Invalid phone number format")
        return phone


class InquiryForm(forms.ModelForm):
    class Meta:
        model = Inquiry
        fields = ['email', 'message']

        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your Email'
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Your message...',
                'rows': 5,
            }),
        }

        labels = {
            'email': 'Email',
            'message': 'Message',
        }