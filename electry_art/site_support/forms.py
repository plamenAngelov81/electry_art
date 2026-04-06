from django import forms

from electry_art.site_support.models import Inquiry


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