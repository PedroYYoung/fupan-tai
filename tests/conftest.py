# -*- coding: utf-8 -*-
import os
import sys

# 让测试可以直接 import scripts/ 下的 build.py 与 modules/*
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
