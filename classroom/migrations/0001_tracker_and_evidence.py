from django.conf import settings
from django.db import migrations, models


def seed_trackers(apps, schema_editor):
    from classroom.tracker import seed_from_paths

    seed_from_paths(
        apps.get_model("roadmap", "LearningPath"),
        apps.get_model("classroom", "ConceptTracker"),
    )


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("roadmap", "0002_alter_pathnode_mastery_threshold"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ConceptTracker",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("concept_id", models.CharField(max_length=80)),
                ("title", models.CharField(max_length=160)),
                ("chapter", models.CharField(blank=True, default="", max_length=120)),
                ("mastery", models.SmallIntegerField(default=0)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("correct", models.PositiveIntegerField(default=0)),
                ("flagged_weak", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="concept_trackers",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "classroom_concept_tracker",
            },
        ),
        migrations.CreateModel(
            name="EvidenceEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("concept_id", models.CharField(blank=True, default="", max_length=80)),
                ("surface", models.CharField(max_length=20)),
                ("specialist", models.CharField(blank=True, default="", max_length=40)),
                ("kind", models.CharField(max_length=20)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="evidence_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "classroom_evidence_event",
                "ordering": ("created_at", "id"),
            },
        ),
        migrations.AddConstraint(
            model_name="concepttracker",
            constraint=models.UniqueConstraint(
                fields=("user", "concept_id"),
                name="classroom_tracker_user_concept",
            ),
        ),
        migrations.AddIndex(
            model_name="evidenceevent",
            index=models.Index(fields=["user", "created_at"], name="classroom_evidence_user_time"),
        ),
        migrations.RunPython(seed_trackers, migrations.RunPython.noop),
    ]
