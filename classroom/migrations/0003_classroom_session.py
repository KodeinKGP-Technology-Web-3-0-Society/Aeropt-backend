from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classroom", "0002_today_decision"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ClassroomSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("surface", models.CharField(max_length=20)),
                ("concept_id", models.CharField(blank=True, default="", max_length=80)),
                ("agent_session_id", models.CharField(blank=True, default="", max_length=80)),
                ("status", models.CharField(default="open", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="classroom_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"db_table": "classroom_session"},
        ),
    ]
