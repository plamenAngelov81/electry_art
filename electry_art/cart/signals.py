from django.dispatch import Signal

# Custom signal: fired only when checkout is completed successfully
# We will pass: order (required), user (optional)
checkout_completed = Signal()
