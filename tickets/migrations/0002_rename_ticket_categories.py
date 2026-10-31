from django.db import migrations, models

# Old category value -> new one, for the booking-platform re-theme.
# feature_request and other keep their values.
FORWARD = {
    'billing': 'payments_refunds',
    'account': 'account_login',
    'bug': 'bug_report',
}
# booking_issues had no old equivalent, so going back it becomes 'other'.
BACKWARD = {new: old for old, new in FORWARD.items()} | {'booking_issues': 'other'}


def _remap(apps, mapping):
    Ticket = apps.get_model('tickets', 'Ticket')
    for old, new in mapping.items():
        Ticket.objects.filter(category=old).update(category=new)


def forwards(apps, schema_editor):
    _remap(apps, FORWARD)


def backwards(apps, schema_editor):
    _remap(apps, BACKWARD)


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ticket',
            name='category',
            field=models.CharField(
                blank=True,
                choices=[
                    ('booking_issues', 'Booking issues'),
                    ('payments_refunds', 'Payments & refunds'),
                    ('account_login', 'Account & login'),
                    ('bug_report', 'Bug report'),
                    ('feature_request', 'Feature request'),
                    ('other', 'Other'),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
