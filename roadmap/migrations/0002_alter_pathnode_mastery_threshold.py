from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("roadmap", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pathnode",
            name="mastery_threshold",
            field=models.SmallIntegerField(default=80),
        ),
    ]
