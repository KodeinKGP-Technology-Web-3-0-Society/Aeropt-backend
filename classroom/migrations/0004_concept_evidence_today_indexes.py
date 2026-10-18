from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classroom", "0003_classroom_session"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddIndex(
            model_name="concepttracker",
            index=models.Index(fields=["concept_id"], name="classroom_tracker_concept"),
        ),
        migrations.AddIndex(
            model_name="evidenceevent",
            index=models.Index(fields=["user", "kind"], name="classroom_evidence_user_kind"),
        ),
        migrations.AddIndex(
            model_name="todaydecision",
            index=models.Index(fields=["user", "for_date"], name="classroom_today_user_date"),
        ),
    ]
