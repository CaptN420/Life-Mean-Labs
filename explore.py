import os
import sys

def explore():
    results = []
    for root, dirs, files in os.walk('.'):
        for f in files:
            results.append(os.path.join(root, f))
    return results

if __name__ == '__main__':
    for r in explore():
        print(r)
