import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserRole(models.TextChoices):
    STUDENT = "student", "Student"
    ADMIN = "admin", "Admin"
    CONTENT_COLLECTOR = "content_collector", "Content Collector"
    REVIEWER = "reviewer", "Reviewer"
    MENTOR = "mentor", "Mentor"


class AccountStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    DELETED = "deleted", "Deleted"


class TargetExam(models.TextChoices):
    JEE_MAINS = "JEE_MAINS", "JEE Mains"
    JEE_ADVANCED = "JEE_ADVANCED", "JEE Advanced"
    BOTH = "BOTH", "Both"


class GradeLevel(models.TextChoices):
    CLASS_11 = "CLASS_11", "Class 11"
    CLASS_12 = "CLASS_12", "Class 12"
    DROPPER = "DROPPER", "Dropper"


class JourneyType(models.TextChoices):
    FRESH_START = "fresh_start", "Fresh Start"
    MID_JOURNEY = "mid_journey", "Mid Journey"
    REVISION_DROPPER = "revision_dropper", "Revision / Dropper"


class LearningSource(models.TextChoices):
    SCHOOL = "school", "School"
    COACHING = "coaching", "Coaching"
    SELF_STUDY = "self_study", "Self Study"
    MIXED = "mixed", "Mixed"


class PreferredDepth(models.TextChoices):
    QUICK = "quick", "Quick"
    STANDARD = "standard", "Standard"
    DEEP = "deep", "Deep"


class OAuthProvider(models.TextChoices):
    GOOGLE = "google", "Google"
    APPLE = "apple", "Apple"


class NotificationType(models.TextChoices):
    STREAK = "STREAK", "Streak"
    RECOMMENDATION = "RECOMMENDATION", "Recommendation"
    ACHIEVEMENT = "ACHIEVEMENT", "Achievement"
    SYSTEM = "SYSTEM", "System"
    REVISION_DUE = "REVISION_DUE", "Revision Due"


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", UserRole.ADMIN)
        extra_fields.setdefault("status", AccountStatus.ACTIVE)
        extra_fields.setdefault("email_verified", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, default="")
    full_name = models.CharField(max_length=120, blank=True, default="")
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.STUDENT)
    status = models.CharField(max_length=20, choices=AccountStatus.choices, default=AccountStatus.ACTIVE)
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    avatar_url = models.TextField(blank=True, default="")
    supabase_user_id = models.UUIDField(null=True, blank=True, unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"
        ordering = ("-created_at",)

    def __str__(self):
        return self.email


class OAuthAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="oauth_accounts")
    provider = models.CharField(max_length=20, choices=OAuthProvider.choices)
    provider_user_id = models.CharField(max_length=255)
    email = models.EmailField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "oauth_accounts"
        ordering = ("-created_at",)
        unique_together = (("provider", "provider_user_id"),)

    def __str__(self):
        return f"{self.provider}:{self.provider_user_id}"


class AuthSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_sessions")
    refresh_token_hash = models.TextField()
    device_info = models.JSONField(default=dict, blank=True)
    ip_address = models.CharField(max_length=45, blank=True, default="")
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "auth_sessions"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user_id}:{self.created_at.isoformat()}"


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name="student_profile")
    target_exam = models.CharField(max_length=20, choices=TargetExam.choices, default=TargetExam.BOTH)
    target_year = models.SmallIntegerField(null=True, blank=True)
    grade_level = models.CharField(max_length=20, choices=GradeLevel.choices, blank=True, default="")
    school_name = models.CharField(max_length=160, blank=True, default="")
    city = models.CharField(max_length=80, blank=True, default="")
    state = models.CharField(max_length=80, blank=True, default="")
    daily_goal_minutes = models.SmallIntegerField(default=30)
    preferred_depth = models.CharField(max_length=20, choices=PreferredDepth.choices, default=PreferredDepth.STANDARD)
    onboarding_completed = models.BooleanField(default=False)
    onboarding_step = models.SmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "student_profiles"

    def __str__(self):
        return f"{self.user_id}:{self.target_exam}"


class UserPreferences(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name="preferences")
    notify_email = models.BooleanField(default=True)
    notify_push = models.BooleanField(default=True)
    notify_revision = models.BooleanField(default=True)
    theme = models.CharField(max_length=20, default="light")
    preferred_language = models.CharField(max_length=10, default="en")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_preferences"

    def __str__(self):
        return f"{self.user_id}:preferences"


class SyllabusPlacement(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name="syllabus_placement")
    journey_type = models.CharField(max_length=24, choices=JourneyType.choices, default=JourneyType.FRESH_START)
    learning_source = models.CharField(max_length=20, choices=LearningSource.choices, default=LearningSource.MIXED)
    covered_chapters = models.JSONField(default=list, blank=True)
    self_assessed_coverage = models.JSONField(default=dict, blank=True)
    diagnostic_baseline = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "syllabus_placement"

    def __str__(self):
        return f"{self.user_id}:{self.journey_type}"


class OnboardingSession(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name="onboarding_session")
    current_step = models.SmallIntegerField(default=1)
    snapshot = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "onboarding_sessions"

    def __str__(self):
        return f"{self.user_id}:step_{self.current_step}"


class Plan(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    price_inr = models.IntegerField(default=0)
    features = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "plans"
        ordering = ("id",)

    def __str__(self):
        return self.name


class Subscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, default="active")
    provider = models.CharField(max_length=30, blank=True, default="")
    external_subscription_id = models.CharField(max_length=120, blank=True, default="")
    started_at = models.DateTimeField()
    current_period_end = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "subscriptions"
        ordering = ("-started_at",)

    def __str__(self):
        return f"{self.user_id}:{self.plan_id}:{self.status}"


class Achievement(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    icon = models.CharField(max_length=60, blank=True, default="")

    class Meta:
        db_table = "achievements"
        ordering = ("id",)

    def __str__(self):
        return self.name


class UserAchievement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_achievements")
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE, related_name="user_achievements")
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_achievements"
        unique_together = (("user", "achievement"),)
        ordering = ("-earned_at",)

    def __str__(self):
        return f"{self.user_id}:{self.achievement_id}"


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=20, choices=NotificationType.choices)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True, default="")
    data = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user_id}:{self.title}"
