# Generated by Django 5.1.2 on 2024-11-12 14:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0008_job_experience'),
    ]

    operations = [
        migrations.AlterField(
            model_name='job',
            name='experience',
            field=models.CharField(max_length=25),
        ),
    ]