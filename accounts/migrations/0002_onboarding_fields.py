from django.db import migrations, models
import django.db.models.deletion


def copy_profiles(apps, schema_editor):
    Legacy = apps.get_model("core", "Profile")
    Profile = apps.get_model("accounts", "Profile")
    db = schema_editor.connection.alias
    for old in Legacy.objects.using(db).iterator():
        Profile.objects.using(db).update_or_create(user_id=old.user_id, defaults={
            "display_name": old.display_name,
            "program_id": old.program_id,
            "photo_reference": old.photo_reference,
            "onboarding_complete": bool(old.display_name.strip() and old.program_id),
        })


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial"), ("core", "0001_initial")]
    operations = [
        migrations.AddField("profile", "display_name", models.CharField(max_length=100, blank=True)),
        migrations.AddField("profile", "photo_reference", models.CharField(max_length=500, blank=True)),
        migrations.AddField("profile", "program", models.ForeignKey(
            to="core.program", on_delete=django.db.models.deletion.PROTECT, null=True, blank=True)),
        migrations.RunPython(copy_profiles, migrations.RunPython.noop),
    ]
