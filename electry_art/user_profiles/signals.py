from django.dispatch import Signal

# Fired when a user successfully registers
# We will pass: user (required)
user_registered = Signal()
