#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
from urllib.parse import quote

outputs = ["## 目录"]


def list_files(path=".", deep=0):
    if deep != 0:
        outputs.append(" " * 4 * (deep - 1) + "1. **" + os.path.split(path)[1] + "**")
    files = os.listdir(path)
    files.sort()
    for f in files:
        fpath = os.path.join(path, f)
        if os.path.isdir(fpath):
            if not f.startswith("."):
                list_files(fpath, deep + 1)
        else:
            if f.lower().endswith(".md") and deep != 0:
                base_name = os.path.splitext(f)[0]
                outputs.append(" " * 4 * deep + "1. [" + base_name + "](" + quote(fpath) + ")")


list_files()

content = ""
for line in outputs:
    content += (line + '\n')

f1 = open('README.md.template', 'r+')
f2 = open('README.md', 'w+')
for ss in f1.readlines():
    tt = re.sub(r"{{content}}", content, ss)
    f2.write(tt)
f1.close()
f2.close()

