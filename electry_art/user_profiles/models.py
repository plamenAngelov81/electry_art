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
    ADDRESS_MAX_LEN = 100
    ADDRESS_MIN_LEN = 5
    PHONE_MAX_LEN = 20
    PHONE_MIN_LEN = 10
    TOWN_MAX_LEN = 30
    TOWN_MIN_LEN = 3
    COUNTRY_MAX_LEN = 30
    COUNTRY_MIN_LEN = 3

    username = models.CharField(
        verbose_name='Username',
        max_length=USER_NAME_MAX_LEN,
        null=False,
        blank=False,
        validators=[MinLengthValidator(USER_NAME_MIN_LEN)],
        unique=True
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
        validators=[MinLengthValidator(FIRST_NAME_MIN_LEN)]
    )

    last_name = models.CharField(
        verbose_name='Last Name',
        max_length=LAST_NAME_MAX_LEN,
        null=True,
        blank=True,
        validators=[MinLengthValidator(LAST_NAME_MIN_LEN)]
    )

    country = models.CharField(
        verbose_name='Country',
        max_length=COUNTRY_MAX_LEN,
        null=True,
        blank=True,
        validators=[MinLengthValidator(COUNTRY_MIN_LEN)]
    )

    town = models.CharField(
        verbose_name='Town',
        max_length=TOWN_MAX_LEN,
        null=True,
        blank=True,
        validators=[MinLengthValidator(TOWN_MIN_LEN)]
    )

    address = models.CharField(
        verbose_name='Address',
        max_length=ADDRESS_MAX_LEN,
        null=True,
        blank=True,
        validators=[MinLengthValidator(ADDRESS_MIN_LEN)]
    )

    phone_num = models.CharField(
        verbose_name='Phone',
        max_length=PHONE_MAX_LEN,
        null=True,
        blank=True,
        validators=[MinLengthValidator(PHONE_MIN_LEN)]
    )

    class Meta:
        verbose_name_plural = 'User Profiles'

    @property
    def get_name(self):
        return f"{self.first_name or ''} {self.last_name or ''}".strip()

    @property
    def get_full_address(self):
        if self.country and self.town and self.address:
            return f'{self.country}, {self.town}, {self.address}'
        return ''