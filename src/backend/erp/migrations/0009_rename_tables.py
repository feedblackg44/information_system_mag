from django.db import migrations


def rename_tables(apps, schema_editor):
    old_prefix = 'crm_'
    new_prefix = 'erp_'
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            SELECT tablename FROM pg_tables WHERE tablename LIKE %s
        """, [old_prefix + '%'])

        for (old_table,) in cursor.fetchall():
            new_table = old_table.replace(old_prefix, new_prefix, 1)
            cursor.execute(f'ALTER TABLE "{old_table}" RENAME TO "{new_table}"')


class Migration(migrations.Migration):

    dependencies = [
        ('erp', '0008_alter_productpricelevel_minimal_quantity_and_more'),
    ]

    operations = [
        migrations.RunPython(rename_tables),
    ]
