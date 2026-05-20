from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MinLengthValidator


class UserProfile(AbstractUser):
    USER_NAME_MAX_LEN = 35
    USER_NAME_MIN_LEN = 5
    FIRST_NAME_MAX_LEN = 30
    FIRST_NAME_MIN_LEN = 3
    LAST_NAME_MAX_LEN = 30
    LAST_NAME_MIN_LEN = 3

    username = models.CharField(
        verbose_name='Username',
        max_length=USER_NAME_MAX_LEN,
        validators=[MinLengthValidator(USER_NAME_MIN_LEN)],
        unique=True,
    )

    email = models.EmailField(
        blank=False,
        null=False,
        unique=True,
    )

    first_name = models.CharField(
        verbose_name='First Name',
        max_length=FIRST_NAME_MAX_LEN,
        null=True,
        blank=True,
        validators=[MinLengthValidator(FIRST_NAME_MIN_LEN)],
    )

    last_name = models.CharField(
        verbose_name='Last Name',
        max_length=LAST_NAME_MAX_LEN,
        null=True,
        blank=True,
        validators=[MinLengthValidator(LAST_NAME_MIN_LEN)],
    )

    class Meta:
        verbose_name_plural = 'User Profiles'

    @property
    def get_name(self):
        return f"{self.first_name or ''} {self.last_name or ''}".strip()


class Address(models.Model):
    COUNTRY_MAX_LEN = 30
    COUNTRY_MIN_LEN = 3
    TOWN_MAX_LEN = 30
    TOWN_MIN_LEN = 3
    ADDRESS_MAX_LEN = 100
    ADDRESS_MIN_LEN = 5
    PHONE_MAX_LEN = 20
    PHONE_MIN_LEN = 10
    COURIER_COMPANY_MAX_LEN = 50
    COURIER_OFFICE_MAX_LEN = 100

    user = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='addresses',
        db_index=True,
    )

    country = models.CharField(
        verbose_name='Country',
        max_length=COUNTRY_MAX_LEN,
        validators=[MinLengthValidator(COUNTRY_MIN_LEN)],
    )

    town = models.CharField(
        verbose_name='Town',
        max_length=TOWN_MAX_LEN,
        validators=[MinLengthValidator(TOWN_MIN_LEN)],
    )

    address = models.CharField(
        verbose_name='Address',
        max_length=ADDRESS_MAX_LEN,
        blank=True,
        validators=[MinLengthValidator(ADDRESS_MIN_LEN)],
    )

    phone_num = models.CharField(
        verbose_name='Phone',
        max_length=PHONE_MAX_LEN,
        validators=[MinLengthValidator(PHONE_MIN_LEN)],
    )

    courier_company = models.CharField(
        verbose_name='Courier Company',
        max_length=COURIER_COMPANY_MAX_LEN,
        blank=True,
    )

    courier_office = models.CharField(
        verbose_name='Courier Office',
        max_length=COURIER_OFFICE_MAX_LEN,
        blank=True,
    )

    is_default = models.BooleanField(
        verbose_name='Default Address',
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        verbose_name_plural = 'Addresses'
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return self.get_full_address

    @property
    def get_full_address(self):
        if self.courier_company and self.courier_office:
            return f'{self.country}, {self.town}, {self.courier_company} office: {self.courier_office}'

        return f'{self.country}, {self.town}, {self.address}'