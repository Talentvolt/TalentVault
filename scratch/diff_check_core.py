import subprocess

def check_diff():
    result = subprocess.run(
        ['git', 'diff', 'apps/core/views.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8'
    )
    
    lines = result.stdout.split('\n')
    print(f"Total diff lines: {len(lines)}")
    
    for i, line in enumerate(lines):
        if line.startswith('+++') or line.startswith('---'):
            print(line)
        elif line.startswith('+') or line.startswith('-'):
            if 'class ' in line or 'Required' in line or 'login' in line or 'auth' in line:
                print(f"{i}: {line}")

if __name__ == '__main__':
    check_diff()
