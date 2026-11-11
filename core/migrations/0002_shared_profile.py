from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial"), ("accounts", "0002_onboarding_fields")]
    operations = [
        # Preserve the old table as a recovery snapshot. Only accounts.Profile is
        # registered with Django. No existing profile rows or files are deleted.
        migrations.SeparateDatabaseAndState(
            database_operations=[], state_operations=[migrations.DeleteModel(name="Profile")]),
        migrations.AddField("school", "is_active", models.BooleanField(default=True)),
        migrations.CreateModel(name="ProfilePhoto", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("object_key", models.CharField(max_length=500, unique=True)),
            ("content_type", models.CharField(max_length=30)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("archived_at", models.DateTimeField(null=True, blank=True)),
            ("profile", models.ForeignKey(to="accounts.profile", on_delete=django.db.models.deletion.PROTECT, related_name="photos")),
        ]),
    ]
