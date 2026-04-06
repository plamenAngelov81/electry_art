from django.db import models

class Inquiry(models.Model):
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Inquiry from {self.email} at {self.created_at.strftime('%Y-%m-%d %H:%M')}"
