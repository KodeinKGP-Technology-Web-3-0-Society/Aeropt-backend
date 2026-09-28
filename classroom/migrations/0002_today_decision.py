from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classroom", "0001_tracker_and_evidence"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TodayDecision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("concept_id", models.CharField(max_length=80)),
                ("for_date", models.DateField()),
                ("status", models.CharField(max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="today_decisions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"db_table": "classroom_today_decision"},
        ),
        migrations.AddConstraint(
            model_name="todaydecision",
            constraint=models.UniqueConstraint(
                fields=("user", "concept_id", "for_date"),
                name="classroom_today_decision_once",
            ),
        ),
    ]
