# Generated manually for Phase 1 onboarding

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_user_supabase_user_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentprofile",
            name="preferred_depth",
            field=models.CharField(
                choices=[("quick", "Quick"), ("standard", "Standard"), ("deep", "Deep")],
                default="standard",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="SyllabusPlacement",
            fields=[
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="syllabus_placement",
                        serialize=False,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "journey_type",
                    models.CharField(
                        choices=[
                            ("fresh_start", "Fresh Start"),
                            ("mid_journey", "Mid Journey"),
                            ("revision_dropper", "Revision / Dropper"),
                        ],
                        default="fresh_start",
                        max_length=24,
                    ),
                ),
                (
                    "learning_source",
                    models.CharField(
                        choices=[
                            ("school", "School"),
                            ("coaching", "Coaching"),
                            ("self_study", "Self Study"),
                            ("mixed", "Mixed"),
                        ],
                        default="mixed",
                        max_length=20,
                    ),
                ),
                ("covered_chapters", models.JSONField(blank=True, default=list)),
                ("self_assessed_coverage", models.JSONField(blank=True, default=dict)),
                ("diagnostic_baseline", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "syllabus_placement",
            },
        ),
        migrations.CreateModel(
            name="OnboardingSession",
            fields=[
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="onboarding_session",
                        serialize=False,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("current_step", models.SmallIntegerField(default=1)),
                ("snapshot", models.JSONField(blank=True, default=dict)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "onboarding_sessions",
            },
        ),
    ]
