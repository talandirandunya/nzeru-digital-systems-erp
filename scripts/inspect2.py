import pathlib, itertools
path = pathlib.Path(r'c:/Users/karlh/Desktop/ERP/ERP/management_system/finance/models.py')
lines = path.read_text().splitlines()
for idx, line in enumerate(lines,1):
    if 'def delete' in line:
        print('---- start at', idx, repr(line))
        # print next 12 lines
        for j in range(idx, min(idx+12, len(lines))):
            print(j, repr(lines[j-1]))
