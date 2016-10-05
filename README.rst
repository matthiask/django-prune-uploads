======================================================
django-prune-uploads - Prune and maintain file uploads
======================================================

Steps
=====

1. Install ``django-prune-uploads`` using pip and add ``prune_uploads``
   to your ``INSTALLED_APPS``.

2. Run ``./manage.py prune_uploads`` and have a look at the output (does
   not change anything in the database or the file system!)

3. Run ``./manage.py prune_uploads -v2`` for a potentially much more
   verbose report.

4. Run ``./manage.py prune_uploads --help`` to learn about the available
   options for actually changing and/or removing files and records.
