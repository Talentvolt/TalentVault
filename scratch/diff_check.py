import subprocess

def check_diff():
    # Run git diff for apps/accounts/views.py
    result = subprocess.run(
        ['git', 'diff', 'apps/accounts/views.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8'
    )
    
    lines = result.stdout.split('\n')
    print(f"Total diff lines: {len(lines)}")
    
    # Print lines that start with + or - and have view definitions
    for i, line in enumerate(lines):
        if line.startswith('+++') or line.startswith('---'):
            print(line)
        elif line.startswith('+') or line.startswith('-'):
            if 'class ' in line or 'def ' in line or 'login(' in line or 'redirect' in line or 'is_authenticated' in line:
                print(f"{i}: {line}")

if __name__ == '__main__':
    check_diff()
