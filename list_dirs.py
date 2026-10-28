import os

workspace = r'C:\Users\celes\Documents\Hermes-Workspace'
life_mean = r'C:\Users\celes\Documents\Hermes-Workspace\Life_mean'

print("=== Hermes-Workspace contents ===")
for item in os.listdir(workspace):
    full_path = os.path.join(workspace, item)
    if os.path.isdir(full_path):
        print(f"[DIR]  {item}/")
    else:
        print(f"     {item}")

print("\n=== Life_mean contents ===")
for item in os.listdir(life_mean):
    full_path = os.path.join(life_mean, item)
    if os.path.isdir(full_path):
        print(f"[DIR]  {item}/")
    else:
        print(f"     {item}")

# Look for mia directories
print("\n=== Looking for mia ===")
for root, dirs, files in os.walk(workspace):
    for d in dirs:
        if 'mia' in d.lower():
            print(os.path.join(root, d))
