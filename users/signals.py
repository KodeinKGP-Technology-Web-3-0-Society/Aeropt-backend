from django.db.models.signals import post_save
from django.dispatch import receiver

from users.models import (
    OnboardingSession,
    StudentProfile,
    SyllabusPlacement,
    User,
    UserPreferences,
    UserRole,
)


@receiver(post_save, sender=User)
def provision_student_records(sender, instance: User, created: bool, **kwargs):
    """Auto-create profile, preferences, placement, and onboarding session on register."""
    if not created or instance.role != UserRole.STUDENT:
        return

    StudentProfile.objects.get_or_create(user=instance)
    UserPreferences.objects.get_or_create(user=instance)
    SyllabusPlacement.objects.get_or_create(user=instance)
    OnboardingSession.objects.get_or_create(user=instance)
