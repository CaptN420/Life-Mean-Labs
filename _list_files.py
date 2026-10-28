import os
from pathlib import Path

base = Path("C:/Users/celes/Documents/Hermes-Workspace/Life_mean")
output = []
for root, dirs, files in os.walk(base):
    level = root.replace(str(base), '').count(os.sep)
    indent = ' ' * 2 * level
    output.append(f'{indent}{os.path.basename(root)}/')
    subindent = ' ' * 2 * (level + 1)
    for file in files:
        if file.endswith('.py'):
            output.append(f'{subindent}{file}')

with open("C:/Users/celes/Documents/Hermes-Workspace/Life_mean/_file_list.txt", "w") as f:
    f.write('\n'.join(output))
