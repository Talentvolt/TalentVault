import os
import json

log_path = r'C:\Users\rajee\.gemini\antigravity-cli\brain\29a242dc-2ab6-49a3-b9c5-cb288a93e7d3\.system_generated\logs\transcript_full.jsonl'
if not os.path.exists(log_path):
    print("Log not found.")
    exit(1)

with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        if '"type":"USER_INPUT"' in line:
            try:
                data = json.loads(line)
                print("=" * 60)
                print("TIMESTAMP:", data.get('created_at'))
                print("CONTENT:", data.get('content'))
            except Exception as e:
                pass
