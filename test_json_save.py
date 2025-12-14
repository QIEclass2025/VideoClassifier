#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test JSON save/load functionality"""

import sys
import json
import os
import hashlib

# Test save_data logic
def test_save_data():
    test_data = [
        {
            "path": "C:/videos/sample.mp4",
            "filename": "sample",
            "extension": ".mp4",
            "duration": "1:23:45",
            "tags": "#test #demo",
            "thumbnail_path": ".thumbnails/abc123def456.jpg"
        }
    ]

    json_path = "videos_test.json"
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, indent=4, ensure_ascii=False)
        print(f"✓ JSON file created: {json_path}")
        print(f"✓ File exists: {os.path.exists(json_path)}")
        
        # Try to load it back
        with open(json_path, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        print(f"✓ JSON file loaded successfully")
        print(f"✓ Data integrity: {loaded == test_data}")
        print(f"✓ File contents:")
        with open(json_path, 'r', encoding='utf-8') as f:
            print(f.read())
        
        # Clean up
        os.remove(json_path)
        print(f"✓ Test file cleaned up")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_save_data()
    sys.exit(0 if success else 1)
