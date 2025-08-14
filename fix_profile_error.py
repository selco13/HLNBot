#!/usr/bin/env python3
import os
import re
import shutil
from datetime import datetime

# Paths to the files we need to fix
formatters_path = '/home/hlnbot/Documents/cogs/profile/formatters.py'
security_path = '/home/hlnbot/Documents/cogs/profile/security.py'

# Create backups before making changes
for path in [formatters_path, security_path]:
    backup_path = f'{path}.bak.{datetime.now().strftime("%Y%m%d%H%M%S")}'
    shutil.copy2(path, backup_path)
    print(f"Created backup at {backup_path}")

# Fix formatters.py first (just in case it still has the issue)
with open(formatters_path, 'r') as f:
    formatters_content = f.read()

formatters_pattern = r'classification,\s*[\*\w]+\s*=\s*get[\w_]*security_classification\(([^)]+)\)'
formatters_replacement = r'classification = get_security_classification(\1)'

if re.search(formatters_pattern, formatters_content):
    fixed_formatters = re.sub(formatters_pattern, formatters_replacement, formatters_content)
    
    with open(formatters_path, 'w') as f:
        f.write(fixed_formatters)
    
    print("Fixed the unpacking issue in formatters.py")
else:
    print("No issue found in formatters.py or it was already fixed")

# Now fix security.py
with open(security_path, 'r') as f:
    security_content = f.read()

# Look for the problematic line in get_clearance_code
security_pattern = r'classification,\s*auth_code\s*=\s*get_security_classification\(([^)]+)\)'
security_replacement = r'classification = get_security_classification(\1)\n    auth_code = classification.auth_code'

if re.search(security_pattern, security_content):
    fixed_security = re.sub(security_pattern, security_replacement, security_content)
    
    with open(security_path, 'w') as f:
        f.write(fixed_security)
    
    print("Fixed the unpacking issue in security.py")
else:
    print("Could not find the expected pattern in security.py. Manual inspection needed.")