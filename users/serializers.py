from rest_framework import serializers

from users.models import (
    Achievement,
    AccountStatus,
    AuthSession,
    Notification,
    OAuthAccount,
    OnboardingSession,
    Plan,
    StudentProfile,
    Subscription,
    SyllabusPlacement,
    User,
    UserAchievement,
    UserPreferences,
    UserRole,
)


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, style={"input_type": "password"})

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "phone",
            "full_name",
            "role",
            "status",
            "email_verified",
            "phone_verified",
            "avatar_url",
            "supabase_user_id",
            "last_login_at",
            "created_at",
            "updated_at",
            "password",
        )
        read_only_fields = ("id", "created_at", "updated_at", "last_login_at", "supabase_user_id")

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request and not request.user.is_staff:
            for field_name in ("role", "status", "email_verified", "phone_verified"):
                if field_name in fields:
                    fields[field_name].read_only = True
        return fields

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        request = self.context.get("request")
        if request and not request.user.is_staff:
            for field_name in ("role", "status", "email_verified", "phone_verified"):
                validated_data.pop(field_name, None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ("email", "password", "full_name")

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    def create(self, validated_data):
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            full_name=validated_data.get("full_name", ""),
            role=UserRole.STUDENT,
            status=AccountStatus.ACTIVE,
        )


class OAuthAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = OAuthAccount
        fields = ("id", "user", "provider", "provider_user_id", "email", "created_at")
        read_only_fields = ("id", "created_at", "user")


class AuthSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthSession
        fields = (
            "id",
            "user",
            "refresh_token_hash",
            "device_info",
            "ip_address",
            "expires_at",
            "revoked_at",
            "created_at",
        )
        read_only_fields = ("id", "created_at", "user")
        extra_kwargs = {"refresh_token_hash": {"write_only": True}}


class StudentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentProfile
        fields = (
            "user",
            "target_exam",
            "target_year",
            "grade_level",
            "school_name",
            "city",
            "state",
            "daily_goal_minutes",
            "preferred_depth",
            "onboarding_completed",
            "onboarding_step",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("user", "created_at", "updated_at")


class SyllabusPlacementSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyllabusPlacement
        fields = (
            "user",
            "journey_type",
            "learning_source",
            "covered_chapters",
            "self_assessed_coverage",
            "diagnostic_baseline",
            "updated_at",
        )
        read_only_fields = ("user", "updated_at")


class OnboardingSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OnboardingSession
        fields = (
            "user",
            "current_step",
            "snapshot",
            "completed_at",
            "updated_at",
        )
        read_only_fields = ("user", "updated_at")


class UserPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreferences
        fields = (
            "user",
            "notify_email",
            "notify_push",
            "notify_revision",
            "theme",
            "preferred_language",
            "updated_at",
        )
        read_only_fields = ("user", "updated_at")


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ("id", "code", "name", "price_inr", "features", "is_active")


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    plan_id = serializers.PrimaryKeyRelatedField(
        queryset=Plan.objects.all(), source="plan", write_only=True
    )

    class Meta:
        model = Subscription
        fields = (
            "id",
            "user",
            "plan",
            "plan_id",
            "status",
            "provider",
            "external_subscription_id",
            "started_at",
            "current_period_end",
            "canceled_at",
        )
        read_only_fields = ("id", "user")


class AchievementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Achievement
        fields = ("id", "code", "name", "description", "icon")


class UserAchievementSerializer(serializers.ModelSerializer):
    achievement = AchievementSerializer(read_only=True)
    achievement_id = serializers.PrimaryKeyRelatedField(
        queryset=Achievement.objects.all(), source="achievement", write_only=True
    )

    class Meta:
        model = UserAchievement
        fields = ("user", "achievement", "achievement_id", "earned_at")
        read_only_fields = ("user", "earned_at")


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = (
            "id",
            "user",
            "type",
            "title",
            "body",
            "data",
            "read_at",
            "created_at",
        )
        read_only_fields = ("id", "created_at", "user")
