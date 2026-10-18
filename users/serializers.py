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


class LeaderboardEntrySerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    user_id = serializers.UUIDField()
    name = serializers.CharField()
    current_streak = serializers.IntegerField()
    highest_streak = serializers.IntegerField()


class MeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    full_name = serializers.CharField(allow_blank=True)
    supabase_user_id = serializers.UUIDField(allow_null=True)
    profile = StudentProfileSerializer()
    placement = SyllabusPlacementSerializer()
    onboarding_session = OnboardingSessionSerializer()
    onboarding_completed = serializers.BooleanField()
    onboarding_step = serializers.IntegerField()


class ChapterMetaSerializer(serializers.Serializer):
    name = serializers.CharField()
    concept_count = serializers.IntegerField()
    order = serializers.IntegerField()


class SubjectUnitSerializer(serializers.Serializer):
    name = serializers.CharField()
    chapters = serializers.ListField(child=serializers.CharField())


class SubjectUnitsSerializer(serializers.Serializer):
    name = serializers.CharField()
    units = SubjectUnitSerializer(many=True)


class OnboardingChaptersSerializer(serializers.Serializer):
    chapters = ChapterMetaSerializer(many=True)
    subjects = SubjectUnitsSerializer(many=True)


class PlacementPlanRequestSerializer(serializers.Serializer):
    journey_type = serializers.CharField(required=False)
    covered_chapters = serializers.ListField(child=serializers.CharField(), required=False)
    self_assessed_coverage = serializers.JSONField(required=False)


class PlacementPlanSerializer(serializers.Serializer):
    probes = serializers.ListField(child=serializers.JSONField())
    total_probes = serializers.IntegerField()
    estimated_minutes = serializers.IntegerField()
    skipped_chapters = serializers.ListField(child=serializers.CharField())
    journey_type = serializers.CharField()


class OnboardingCompleteProfileSerializer(serializers.Serializer):
    target_exam = serializers.CharField(required=False)
    target_year = serializers.IntegerField(required=False, allow_null=True)
    grade_level = serializers.CharField(required=False)
    daily_goal_minutes = serializers.IntegerField(required=False)
    preferred_depth = serializers.CharField(required=False)
    onboarding_step = serializers.IntegerField(required=False)


class OnboardingCompletePlacementSerializer(serializers.Serializer):
    journey_type = serializers.CharField(required=False)
    learning_source = serializers.CharField(required=False, allow_blank=True)
    covered_chapters = serializers.ListField(child=serializers.CharField(), required=False)
    self_assessed_coverage = serializers.JSONField(required=False)
    diagnostic_baseline = serializers.JSONField(required=False)


class OnboardingCompleteRequestSerializer(serializers.Serializer):
    profile = OnboardingCompleteProfileSerializer(required=False)
    placement = OnboardingCompletePlacementSerializer(required=False)
    snapshot = serializers.JSONField(required=False)
    current_step = serializers.IntegerField(required=False)
    onboarding_step = serializers.IntegerField(required=False)


class OnboardingCompleteResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    onboarding_completed = serializers.BooleanField()
    sandbox = serializers.JSONField()
    roadmap = serializers.JSONField(allow_null=True)


class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()
