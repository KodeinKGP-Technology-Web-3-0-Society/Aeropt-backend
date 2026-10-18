from rest_framework import serializers


class ClassroomTodaySerializer(serializers.Serializer):
    concept_id = serializers.CharField()
    title = serializers.CharField()
    action = serializers.CharField()
    minutes = serializers.IntegerField()
    provisional = serializers.BooleanField(required=False)


class ClassroomPlanItemSerializer(serializers.Serializer):
    concept_id = serializers.CharField()
    title = serializers.CharField()
    status = serializers.CharField()
    when = serializers.CharField()
    chapter = serializers.CharField(required=False, allow_blank=True)
    estimated_minutes = serializers.IntegerField(required=False)


class ClassroomMapItemSerializer(serializers.Serializer):
    concept_id = serializers.CharField()
    title = serializers.CharField()
    chapter = serializers.CharField(allow_blank=True)
    mastery = serializers.IntegerField()
    prereqs = serializers.ListField(child=serializers.CharField())


class ClassroomReviseItemSerializer(serializers.Serializer):
    concept_id = serializers.CharField()
    title = serializers.CharField()
    due = serializers.CharField()


class ClassroomReadinessSerializer(serializers.Serializer):
    score = serializers.IntegerField()
    label = serializers.CharField()


class ClassroomStreakDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    active = serializers.BooleanField()
    is_today = serializers.BooleanField()


class ClassroomStreakSerializer(serializers.Serializer):
    current_streak = serializers.IntegerField()
    week = ClassroomStreakDaySerializer(many=True)


class ClassroomInsightSerializer(serializers.Serializer):
    type = serializers.CharField()
    title = serializers.CharField()
    body = serializers.CharField()
    action = serializers.CharField()
    action_label = serializers.CharField()
    count = serializers.IntegerField(required=False)


class ClassroomSubjectMasterySerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    color = serializers.CharField()
    active = serializers.BooleanField()
    mastery = serializers.IntegerField()
    total = serializers.IntegerField()
    mastered = serializers.IntegerField()
    coming_soon = serializers.BooleanField(required=False)


class ClassroomHomeSerializer(serializers.Serializer):
    today = ClassroomTodaySerializer(allow_null=True)
    plan = ClassroomPlanItemSerializer(many=True)
    map = ClassroomMapItemSerializer(many=True)
    revise = ClassroomReviseItemSerializer(many=True)
    readiness = ClassroomReadinessSerializer()
    streak = ClassroomStreakSerializer()
    insights = ClassroomInsightSerializer(many=True)
    subject_mastery = ClassroomSubjectMasterySerializer(many=True)


class ClassroomEvidenceRequestSerializer(serializers.Serializer):
    concept_id = serializers.CharField(required=False, allow_blank=True)
    surface = serializers.CharField()
    specialist = serializers.CharField(required=False, allow_blank=True)
    kind = serializers.CharField()
    payload = serializers.JSONField(required=False)


class ClassroomEvidenceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    concept_id = serializers.CharField(allow_blank=True)
    kind = serializers.CharField()


class ClassroomSessionRequestSerializer(serializers.Serializer):
    surface = serializers.CharField()
    concept_id = serializers.CharField(required=False, allow_blank=True)
    agent_session_id = serializers.CharField(required=False, allow_blank=True)


class ClassroomSessionSerializer(serializers.Serializer):
    surface = serializers.CharField()
    concept_id = serializers.CharField(allow_blank=True)
    agent_session_id = serializers.CharField(allow_blank=True)
    status = serializers.CharField()


class CalendarEntrySerializer(serializers.Serializer):
    date = serializers.DateField()
    concept_id = serializers.CharField()
    title = serializers.CharField()
    chapter = serializers.CharField(allow_blank=True)
    estimated_minutes = serializers.IntegerField()
