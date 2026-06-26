from rest_framework import serializers

from users.models import (
    Achievement,
    AuthSession,
    Notification,
    OAuthAccount,
    Plan,
    StudentProfile,
    Subscription,
    User,
    UserAchievement,
    UserPreferences,
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
            "last_login_at",
            "created_at",
            "updated_at",
            "password",
        )
        read_only_fields = ("id", "created_at", "updated_at", "last_login_at")

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
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class OAuthAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = OAuthAccount
        fields = ("id", "user", "provider", "provider_user_id", "email", "created_at")
        read_only_fields = ("id", "created_at")


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
        read_only_fields = ("id", "created_at")
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
            "onboarding_completed",
            "onboarding_step",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")


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
        read_only_fields = ("updated_at",)


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
        read_only_fields = ("id",)


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
        read_only_fields = ("earned_at",)


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
        read_only_fields = ("id", "created_at")
