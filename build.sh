#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
# Compile translations — use Django's compilemessages if msgfmt is available,
# otherwise fall back to polib (pure Python, no system dependency)
if command -v msgfmt &> /dev/null; then
  python management_system/manage.py compilemessages --locale fr
else
  python -c "
import polib, pathlib
for po_path in pathlib.Path('management_system/locale').rglob('*.po'):
    po = polib.pofile(str(po_path))
    po.save_as_mofile(str(po_path.with_suffix('.mo')))
    print(f'Compiled {po_path} ({len(po.translated_entries())} strings)')
"
fi
python management_system/manage.py collectstatic --noinput
python management_system/manage.py migrate --noinput
