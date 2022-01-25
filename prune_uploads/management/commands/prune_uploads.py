import os
import re
from collections import defaultdict

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import FileField


EXCLUDE_DIRS = [
    r"^__.+__$",
]


class Command(BaseCommand):
    help = "Manage uploads"

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete-orphans",
            action="store_true",
            help="Delete orphaned files.",
        )
        parser.add_argument(
            "--blank-missing",
            action="append",
            metavar="app.model.field",
            default=[],
            help=(
                "Empty blank file field <app.model.field> if referenced"
                " media file is missing."
            ),
        )
        parser.add_argument(
            "--delete-invalid",
            action="append",
            metavar="app.model.field",
            default=[],
            help=(
                "Delete instances where <app.model.field> references a"
                " non-existing media file."
            ),
        )

    def handle(self, **options):
        filefields = defaultdict(list)

        delete_invalid_names = {f.lower() for f in options["delete_invalid"]}
        delete_invalid_fields = set()

        blank_missing_names = {f.lower() for f in options["blank_missing"]}
        blank_missing_fields = set()

        for model in apps.get_models():
            for field in model._meta.get_fields():
                if not isinstance(field, FileField):
                    continue

                filefields[model].append(field)
                key = f"{model._meta.label_lower}.{field.name.lower()}"
                if key in delete_invalid_names:
                    delete_invalid_names.remove(key)
                    delete_invalid_fields.add(field)
                if key in blank_missing_names:
                    blank_missing_names.remove(key)
                    blank_missing_fields.add(field)

        if delete_invalid_names:
            raise Exception("delete-invalid: Invalid fields %r" % delete_invalid_names)
        if blank_missing_names:
            raise Exception("blank-missing: Invalid fields %r" % blank_missing_names)

        self.stdout.write("\n")
        self.stdout.write("#" * 79)
        self.stdout.write("File fields:")
        self.stdout.write(
            "\n".join(
                sorted(
                    "{}: {}".format(
                        model._meta.label, ", ".join(field.name for field in fields)
                    )
                    for model, fields in filefields.items()
                )
            )
        )
        self.stdout.write()

        known_with_source = {}

        for model, fields in filefields.items():
            for row in model._default_manager.order_by().values_list(
                "id", *[field.name for field in fields]
            ):
                for idx, name in enumerate(row[1:]):
                    if name:
                        known_with_source[name] = (model, fields[idx], row[0])

        known = set(known_with_source.keys())

        self.stdout.write("\n")
        self.stdout.write("#" * 79)
        self.stdout.write("Known media files: %d" % len(known))

        existing = set()
        for dirpath, dirnames, filenames in os.walk(
            settings.MEDIA_ROOT, followlinks=True
        ):
            for idx in range(len(dirnames) - 1, -1, -1):
                for exclude in EXCLUDE_DIRS:
                    if re.match(exclude, dirnames[idx]):
                        del dirnames[idx]

            existing |= {os.path.join(dirpath, name) for name in filenames}

        media_root = str(settings.MEDIA_ROOT)
        existing = {
            e[len(media_root) :].lstrip("/")
            for e in existing
            if e.startswith(media_root)
        }

        self.stdout.write("Found media files: %d" % len(existing))

        self.stdout.write("\n")
        self.stdout.write("#" * 79)
        self.stdout.write(
            "Media files not in file system: %d" % (len(known - existing))
        )
        missing = defaultdict(list)

        for name in sorted(known - existing):
            model, field, pk = known_with_source[name]

            if field.blank and field in blank_missing_fields:
                self.stdout.write(
                    "Emptying {}.{} of {} ({})".format(
                        model._meta.label, field.name, pk, name
                    )
                )
                model._default_manager.filter(pk=pk).update(
                    **{
                        field.name: "",
                    }
                )

            elif field in delete_invalid_fields:
                self.stdout.write(
                    "Deleting {} of {} because of invalid {} ({})".format(
                        model._meta.label, pk, field.name, name
                    )
                )
                model._default_manager.filter(pk=pk).delete()

            else:
                missing[(model, field)].append(name)

        for key, value in missing.items():
            self.stdout.write(
                "{}.{}: {}".format(
                    key[0]._meta.label,
                    key[1].name,
                    len(value),
                )
            )
            if options["verbosity"] > 1:
                self.stdout.write("\n".join(sorted(value)))
                self.stdout.write()

        self.stdout.write("\n")
        self.stdout.write("#" * 79)
        self.stdout.write("Media files not in DB: %d" % (len(existing - known)))

        if options["delete_orphans"]:
            for name in sorted(existing - known):
                self.stdout.write(f"Deleting {name}")
                os.remove(os.path.join(settings.MEDIA_ROOT, name))
        else:
            if options["verbosity"] > 1:
                self.stdout.write("\n".join(sorted(existing - known)))
