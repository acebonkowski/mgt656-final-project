from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_profile_username")]
    operations = [
        migrations.AddField(
            model_name="profile",
            name="attendance_visibility",
            field=models.CharField(
                choices=[
                    ("friends", "Friends"),
                    ("program", "My program"),
                    ("school", "My school"),
                    ("everyone", "Everyone"),
                ],
                default="everyone",
                max_length=10,
            ),
        ),
    ]
