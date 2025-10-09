#!/usr/bin/env python3
"""
Helper script to identify Chinese text in Python files for translation.
This script finds all lines containing Chinese characters.
"""

import re
import sys

def has_chinese(text):
    """Check if text contains Chinese characters"""
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def find_chinese_in_file(filepath):
    """Find all lines with Chinese text in a file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        chinese_lines = []
        for i, line in enumerate(lines, 1):
            if has_chinese(line):
                chinese_lines.append((i, line.rstrip()))

        return chinese_lines
    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
        return []

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python translate_helper.py <file1.py> [file2.py ...]")
        sys.exit(1)

    for filepath in sys.argv[1:]:
        print(f"\n{'='*60}")
        print(f"File: {filepath}")
        print('='*60)

        chinese_lines = find_chinese_in_file(filepath)

        if chinese_lines:
            for line_num, line in chinese_lines:
                print(f"{line_num:4d}: {line}")
        else:
            print("No Chinese text found")
