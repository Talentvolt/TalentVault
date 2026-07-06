import os
import json

log_path = r'C:\Users\rajee\.gemini\antigravity-cli\brain\29a242dc-2ab6-49a3-b9c5-cb288a93e7d3\.system_generated\logs\transcript_full.jsonl'
if not os.path.exists(log_path):
    print("Log not found.")
    exit(1)

with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        if 'SAVE_FAILED' in line or 'Database save failed' in line or 'DATABASE SAVE FAILURE' in line or 'db_index' in line:
            # Print a chunk of the line containing it
            try:
                data = json.loads(line)
                content = data.get('content', '')
                if 'Traceback' in content or 'Error' in content or 'Exception' in content or 'IntegrityError' in content:
                    print("=" * 80)
                    print("FOUND IN STEP:", data.get('step_index'))
                    print("CONTENT SHORT:")
                    print(content[:3000]) # Print first 3000 chars of content
            except Exception as e:
                pass
