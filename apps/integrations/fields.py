from django.db import models
from django.conf import settings
from django.core.signing import Signer
import json

class EncryptedField(models.TextField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.signer = Signer()

    def get_prep_value(self, value):
        if value is None:
            return value
        # Convert any non-string values to JSON string before encryption
        if not isinstance(value, str):
            value = json.dumps(value)
        return self.signer.sign(value)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        try:
            return self.signer.unsign(value)
        except:
            return value

    def to_python(self, value):
        if value is None:
            return value
        try:
            # If the value is already decrypted, return it
            if not isinstance(value, str) or not value.startswith(':'):
                return value
            return self.signer.unsign(value)
        except:
            return value