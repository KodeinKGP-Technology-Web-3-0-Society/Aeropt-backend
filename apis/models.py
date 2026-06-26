import uuid

from django.db import models


class ContentType(models.TextChoices):
    THEORY = "THEORY", "Theory"
    SOLVED_EXAMPLE = "SOLVED_EXAMPLE", "Solved Example"
    PRACTICE_QUESTION = "PRACTICE_QUESTION", "Practice Question"
    PYQ = "PYQ", "PYQ"


class SourceBook(models.TextChoices):
    HCV = "HCV", "HC Verma"
    DC_PANDEY = "DC_PANDEY", "DC Pandey"
    IRODOV = "IRODOV", "Irodov"
    PYQ = "PYQ", "PYQ"


class QuestionType(models.TextChoices):
    SCQ = "SCQ", "Single Choice"
    MCQ = "MCQ", "Multiple Choice"
    NUMERICAL = "NUMERICAL", "Numerical"
    ASSERTION_REASON = "ASSERTION_REASON", "Assertion Reason"
    COMPREHENSION = "COMPREHENSION", "Comprehension"


class ExamPaper(models.TextChoices):
    MAINS = "MAINS", "Mains"
    ADVANCED = "ADVANCED", "Advanced"


class TargetExam(models.TextChoices):
    JEE_MAINS = "JEE_MAINS", "JEE Mains"
    JEE_ADVANCED = "JEE_ADVANCED", "JEE Advanced"
    BOTH = "BOTH", "Both"


class FlagStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    TRIAGED = "TRIAGED", "Triaged"
    RESOLVED = "RESOLVED", "Resolved"
    DISMISSED = "DISMISSED", "Dismissed"


class Subject(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=40)
    slug = models.CharField(max_length=40, unique=True)
    order_index = models.SmallIntegerField(default=0)

    class Meta:
        db_table = "subjects"
        ordering = ("order_index", "id")

    def __str__(self):
        return self.name


class Chapter(models.Model):
    id = models.AutoField(primary_key=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="chapters")
    name = models.CharField(max_length=120)
    slug = models.CharField(max_length=120)
    order_index = models.SmallIntegerField(default=0)

    class Meta:
        db_table = "chapters"
        ordering = ("order_index", "id")
        unique_together = (("subject", "slug"),)

    def __str__(self):
        return self.name


class Concept(models.Model):
    id = models.AutoField(primary_key=True)
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="concepts")
    name = models.CharField(max_length=120)
    slug = models.CharField(max_length=120)
    order_index = models.SmallIntegerField(default=0)

    class Meta:
        db_table = "concepts"
        ordering = ("order_index", "id")
        unique_together = (("chapter", "slug"),)

    def __str__(self):
        return self.name


class ConceptPrerequisite(models.Model):
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="prerequisites")
    prerequisite_concept = models.ForeignKey(
        Concept, on_delete=models.CASCADE, related_name="required_for"
    )

    class Meta:
        db_table = "concept_prerequisites"
        unique_together = (("concept", "prerequisite_concept"),)

    def __str__(self):
        return f"{self.concept_id} <- {self.prerequisite_concept_id}"


class ContentItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vector_id = models.CharField(max_length=128, blank=True, default="")
    external_row_id = models.CharField(max_length=64, blank=True, default="")
    content_type = models.CharField(max_length=30, choices=ContentType.choices)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="content_items")
    chapter = models.ForeignKey(Chapter, on_delete=models.PROTECT, related_name="content_items")
    primary_concept = models.ForeignKey(
        Concept, on_delete=models.PROTECT, related_name="primary_content_items"
    )
    source_book = models.CharField(max_length=20, choices=SourceBook.choices, blank=True, default="")
    page_number = models.CharField(max_length=20, blank=True, default="")
    difficulty = models.SmallIntegerField(default=1)
    question_type = models.CharField(max_length=30, choices=QuestionType.choices, blank=True, default="")
    jee_year = models.SmallIntegerField(null=True, blank=True)
    exam_type = models.CharField(max_length=20, choices=ExamPaper.choices, blank=True, default="")
    target_exam = models.CharField(max_length=20, choices=TargetExam.choices, blank=True, default="")
    has_diagram = models.BooleanField(default=False)
    diagram_image_key = models.TextField(blank=True, default="")
    solution_image_key = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "content_items"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.id}:{self.content_type}"


class ContentSecondaryConcept(models.Model):
    content_item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="secondary_concepts")
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="secondary_content_items")

    class Meta:
        db_table = "content_secondary_concepts"
        unique_together = (("content_item", "concept"),)

    def __str__(self):
        return f"{self.content_item_id}:{self.concept_id}"


class ContentFlag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content_item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="flags")
    reported_by = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="content_flags_reported"
    )
    reason = models.CharField(max_length=280)
    status = models.CharField(max_length=20, choices=FlagStatus.choices, default=FlagStatus.OPEN)
    resolved_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="content_flags_resolved",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "content_flags"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.content_item_id}:{self.status}"
