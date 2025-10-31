from django.db import models
from django.conf import settings

class Person(models.Model):
    """
    Represents an individual (e.g., investor, tenant) undergoing compliance checks.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_review', 'In Review'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True, help_text="The person's email address.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.first_name} {self.last_name}'

class Document(models.Model):
    """
    Stores KYC documents associated with a Person.
    """
    DOCUMENT_TYPE_CHOICES = [
        ('passport', 'Passport'),
        ('proof_of_address', 'Proof of Address'),
        ('accountant_letter', 'Accountant Letter'),
        ('other', 'Other'),
    ]

    person = models.ForeignKey(Person, related_name='documents', on_delete=models.CASCADE)
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPE_CHOICES)
    file = models.FileField(upload_to='compliance_documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The team member who uploaded the document."
    )

    def __str__(self):
        return f'{self.get_document_type_display()} for {self.person}'

class ActionLog(models.Model):
    """
    Records an audit trail of compliance actions for a Person.
    """
    person = models.ForeignKey(Person, related_name='action_logs', on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The team member who performed the action."
    )
    action = models.CharField(max_length=255, help_text="A description of the action taken.")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f'"{self.action}" for {self.person} at {self.timestamp.strftime("%Y-%m-%d %H:%M")}'
