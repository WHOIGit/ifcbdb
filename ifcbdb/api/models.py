import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from .scopes import scopes_allow

RAW_KEY_PREFIX = "ifcb_"


class ApiKeyManager(models.Manager):
    def create_key(self, user, name, scopes, description="", expires_at=None):
        """Create an API key. Returns (raw_key, api_key); the raw key is
        only ever shown once (at creation), the database stores a hash."""
        prefix = secrets.token_urlsafe(8)[:8]
        secret = secrets.token_urlsafe(48)
        hashed_key = hashlib.sha256(secret.encode()).hexdigest()
        api_key = self.create(
            user=user,
            name=name,
            description=description,
            prefix=prefix,
            hashed_key=hashed_key,
            scopes=scopes,
            expires_at=expires_at,
        )
        raw_key = f"{RAW_KEY_PREFIX}{prefix}.{secret}"
        return raw_key, api_key

    def authenticate(self, raw_key):
        "Return the valid ApiKey for a raw key, or None if it is unknown or invalid."
        if not raw_key or "." not in raw_key:
            return None

        key_id, _, secret = raw_key.partition(".")
        prefix = key_id[len(RAW_KEY_PREFIX):] if key_id.startswith(RAW_KEY_PREFIX) else key_id

        api_key = self.filter(prefix=prefix).first()
        if api_key is None:
            return None

        hashed = hashlib.sha256(secret.encode()).hexdigest()
        if not constant_time_compare(hashed, api_key.hashed_key):
            return None

        if not api_key.is_valid:
            return None

        # record usage, but only update at most once per minute to reduce writes
        now = timezone.now()
        if (
            api_key.last_used_at is None
            or api_key.last_used_at < now - timedelta(minutes=1)
        ):
            api_key.last_used_at = now
            api_key.save(update_fields=["last_used_at"])

        return api_key


class ApiKey(models.Model):
    "A per-user API key for the dashboard API, with a set of granted scopes."

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    prefix = models.CharField(max_length=8, unique=True)
    hashed_key = models.CharField(max_length=64)
    scopes = models.JSONField(default=list)
    revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    objects = ApiKeyManager()

    class Meta:
        ordering = ["name"]
        verbose_name = "API key"
        verbose_name_plural = "API keys"

    def __str__(self):
        return f"{self.user.get_username()}<{self.prefix}>"

    @property
    def is_expired(self):
        if self.expires_at is None:
            return False
        return self.expires_at < timezone.now()

    @property
    def is_valid(self):
        if self.revoked or self.is_expired:
            return False
        if self.user_id is None or not self.user.is_active:
            return False
        return True

    def has_scope(self, scope):
        return scopes_allow(self.scopes, scope)
