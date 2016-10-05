from collections import defaultdict
import os
import re

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import FileField


EXCLUDE_DIRS = [
    r'^__.+__$',
]


class Command(BaseCommand):
    help = 'Manage uploads'

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete-orphans',
            action='store_true',
            help='Delete orphaned files.',
        )
        parser.add_argument(
            '--nullify-missing',
            action='append',
            metavar='app.model.field',
            default=[],
            help=(
                'Empty nullable file field <app.model.field> if referenced'
                ' media file is missing.'
            ),
        )
        parser.add_argument(
            '--delete-invalid',
            action='append',
            metavar='app.model.field',
            default=[],
            help=(
                'Delete instances where <app.model.field> references a'
                ' non-existing media file.'
            ),
        )

    def handle(self, **options):
        filefields = defaultdict(list)

        delete_invalid_names = {f.lower() for f in options['delete_invalid']}
        delete_invalid_fields = set()

        nullify_missing_names = {f.lower() for f in options['nullify_missing']}
        nullify_missing_fields = set()

        for model in apps.get_models():
            for field in model._meta.get_fields():
                if not isinstance(field, FileField):
                    continue

                filefields[model].append(field)
                key = '%s.%s' % (model._meta.label_lower, field.name.lower())
                if key in delete_invalid_names:
                    delete_invalid_names.remove(key)
                    delete_invalid_fields.add(field)
                if key in nullify_missing_names:
                    nullify_missing_names.remove(key)
                    nullify_missing_fields.add(field)

        if delete_invalid_names:
            raise Exception(
                'delete-invalid: Invalid fields %r' % delete_invalid_names)
        if nullify_missing_names:
            raise Exception(
                'nullify-missing: Invalid fields %r' % nullify_missing_names)

        print('\n')
        print('#' * 79)
        print('File fields:')
        print('\n'.join(sorted('%s: %s' % (
            model._meta.label,
            ', '.join(field.name for field in fields)
        ) for model, fields in filefields.items())))
        print()

        known_with_source = {}

        for model, fields in filefields.items():
            for row in model._default_manager.order_by().values_list('id', *[
                field.name for field in fields
            ]):
                for idx, name in enumerate(row[1:]):
                    if name:
                        known_with_source[name] = (model, fields[idx], row[0])

        known = set(known_with_source.keys())

        print('\n')
        print('#' * 79)
        print('Known media files: %d' % len(known))

        existing = set()
        for dirpath, dirnames, filenames in os.walk(
                settings.MEDIA_ROOT, followlinks=True):
            for idx in range(len(dirnames) - 1, -1, -1):
                for exclude in EXCLUDE_DIRS:
                    if re.match(exclude, dirnames[idx]):
                        del dirnames[idx]

            existing |= {os.path.join(dirpath, name) for name in filenames}

        existing = set(
            e[len(settings.MEDIA_ROOT):].lstrip('/')
            for e in existing if e.startswith(settings.MEDIA_ROOT)
        )

        print('Found media files: %d' % len(existing))

        print('\n')
        print('#' * 79)
        print('Media files not in file system: %d' % (len(known - existing)))
        missing = defaultdict(list)

        for name in sorted(known - existing):
            model, field, pk = known_with_source[name]

            if field.blank and field in nullify_missing_fields:
                print('Emptying %s.%s of %s (%s)' % (
                    model._meta.label, field.name, pk, name))
                model._default_manager.filter(pk=pk).update(**{
                    field.name: '',
                })

            elif field in delete_invalid_fields:
                print('Deleting %s of %s because of invalid %s (%s)' % (
                    model._meta.label, pk, field.name, name))
                model._default_manager.filter(pk=pk).delete()

            else:
                missing[(model, field)].append(name)

        for key, value in missing.items():
            print('%s.%s: %s' % (
                key[0]._meta.label,
                key[1].name,
                len(value),
            ))
            if options['verbosity'] > 1:
                print('\n'.join(sorted(value)))
                print()

        print('\n')
        print('#' * 79)
        print('Media files not in DB: %d' % (len(existing - known)))

        if options['delete_orphans']:
            for name in sorted(existing - known):
                print('Deleting %s' % (name,))
                os.remove(os.path.join(settings.MEDIA_ROOT, name))
        else:
            if options['verbosity'] > 1:
                print('\n'.join(sorted(existing - known)))
