import uuid

from django.conf import settings
from django.db import models


class NodeType(models.TextChoices):
    LEARN = "LEARN", "Learn"
    REVISE = "REVISE", "Revise"
    MASTERED = "MASTERED", "Mastered"


class NodeStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    SKIPPED = "skipped", "Skipped"


class ExamWeight(models.TextChoices):
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"


class LearningPath(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="learning_paths")
    subject = models.CharField(max_length=40, default="Physics")
    total_nodes = models.SmallIntegerField(default=0)
    active_nodes = models.SmallIntegerField(default=0)
    estimated_weeks = models.SmallIntegerField(default=8)
    daily_goal_minutes = models.SmallIntegerField(default=45)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "learning_paths"
        ordering = ("-updated_at",)
        indexes = [
            models.Index(fields=["user", "subject", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.subject}"


class PathNode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    learning_path = models.ForeignKey(LearningPath, on_delete=models.CASCADE, related_name="nodes")
    sequence_index = models.SmallIntegerField()
    concept_id = models.CharField(max_length=80)
    concept_name = models.CharField(max_length=160)
    chapter = models.CharField(max_length=120)
    node_type = models.CharField(max_length=20, choices=NodeType.choices, default=NodeType.LEARN)
    exam_weight = models.CharField(max_length=10, choices=ExamWeight.choices, default=ExamWeight.MEDIUM)
    content_sequence = models.JSONField(default=list, blank=True)
    mastery_threshold = models.SmallIntegerField(default=75)
    estimated_minutes = models.SmallIntegerField(default=12)
    proficiency_pct = models.SmallIntegerField(default=50)
    status = models.CharField(max_length=20, choices=NodeStatus.choices, default=NodeStatus.PENDING)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "path_nodes"
        ordering = ("sequence_index",)
        unique_together = (("learning_path", "concept_id"),)
        indexes = [
            models.Index(fields=["learning_path", "status"]),
        ]

    def __str__(self):
        return f"{self.sequence_index}:{self.concept_id}"


class PathProgress(models.Model):
    """Audit log when a student advances on the path."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="path_progress")
    path_node = models.ForeignKey(PathNode, on_delete=models.CASCADE, related_name="progress_events")
    status = models.CharField(max_length=20, choices=NodeStatus.choices)
    proficiency_pct = models.SmallIntegerField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "path_progress"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user_id}:{self.path_node_id}:{self.status}"
