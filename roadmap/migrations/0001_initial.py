from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("users", "0003_onboarding_phase1"),
    ]

    operations = [
        migrations.CreateModel(
            name="LearningPath",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("subject", models.CharField(default="Physics", max_length=40)),
                ("total_nodes", models.SmallIntegerField(default=0)),
                ("active_nodes", models.SmallIntegerField(default=0)),
                ("estimated_weeks", models.SmallIntegerField(default=8)),
                ("daily_goal_minutes", models.SmallIntegerField(default=45)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="learning_paths",
                        to="users.user",
                    ),
                ),
            ],
            options={
                "db_table": "learning_paths",
                "ordering": ("-updated_at",),
            },
        ),
        migrations.CreateModel(
            name="PathNode",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("sequence_index", models.SmallIntegerField()),
                ("concept_id", models.CharField(max_length=80)),
                ("concept_name", models.CharField(max_length=160)),
                ("chapter", models.CharField(max_length=120)),
                (
                    "node_type",
                    models.CharField(
                        choices=[("LEARN", "Learn"), ("REVISE", "Revise"), ("MASTERED", "Mastered")],
                        default="LEARN",
                        max_length=20,
                    ),
                ),
                (
                    "exam_weight",
                    models.CharField(
                        choices=[("high", "High"), ("medium", "Medium"), ("low", "Low")],
                        default="medium",
                        max_length=10,
                    ),
                ),
                ("content_sequence", models.JSONField(blank=True, default=list)),
                ("mastery_threshold", models.SmallIntegerField(default=75)),
                ("estimated_minutes", models.SmallIntegerField(default=12)),
                ("proficiency_pct", models.SmallIntegerField(default=50)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("in_progress", "In Progress"),
                            ("completed", "Completed"),
                            ("skipped", "Skipped"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "learning_path",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="nodes",
                        to="roadmap.learningpath",
                    ),
                ),
            ],
            options={
                "db_table": "path_nodes",
                "ordering": ("sequence_index",),
                "unique_together": {("learning_path", "concept_id")},
            },
        ),
        migrations.CreateModel(
            name="PathProgress",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("in_progress", "In Progress"),
                            ("completed", "Completed"),
                            ("skipped", "Skipped"),
                        ],
                        max_length=20,
                    ),
                ),
                ("proficiency_pct", models.SmallIntegerField(blank=True, null=True)),
                ("note", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "path_node",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="progress_events",
                        to="roadmap.pathnode",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="path_progress",
                        to="users.user",
                    ),
                ),
            ],
            options={
                "db_table": "path_progress",
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="learningpath",
            index=models.Index(fields=["user", "subject", "is_active"], name="learning_pa_user_id_6f0f0d_idx"),
        ),
        migrations.AddIndex(
            model_name="pathnode",
            index=models.Index(fields=["learning_path", "status"], name="path_nodes_learnin_5fd0b1_idx"),
        ),
    ]
