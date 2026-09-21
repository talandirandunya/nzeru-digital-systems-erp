import pathlib
path = r'c:\Users\karlh\Desktop\ERP\ERP\management_system\finance\models.py'
lines = pathlib.Path(path).read_text().splitlines()
for idx, line in enumerate(lines):
    if 'revert balance' in line:
        print(idx+1, repr(line))
    if 'super().delete' in line and 'revert' in line:
        print('delete line', idx+1)
