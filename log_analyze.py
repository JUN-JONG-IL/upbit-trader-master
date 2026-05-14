#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple analyzer: finds connection ids that were acquired (get) but not returned (put)
in a log file. It matches both pool and connector debug patterns.

Usage:
    python log_analyze.py path/to/logfile.log
"""
import re
import sys
from collections import defaultdict

GET_PATTERNS = [
    re.compile(r"\[Pool\.DEBUG\] getconn acquired id=(\d+)"),
    re.compile(r"\[TimescaleDB\.DEBUG\] 전역 풀에서 연결 획득 id=(\d+)"),
    re.compile(r"\[TimescaleDB\.DEBUG\] 로컬 풀에서 연결 획득 id=(\d+)"),
    re.compile(r"\[TimescaleDB\.DEBUG\] 단일 self\.conn 사용 id=(\d+)"),
    re.compile(r"\[TimescaleDB\.DEBUG\] get_connection id=(\d+)"),
]
PUT_PATTERNS = [
    re.compile(r"\[Pool\.DEBUG\] putconn called id=(\d+)"),
    re.compile(r"\[Pool\] 연결 반환 완료 .* id=(\d+)"),
    re.compile(r"\[TimescaleDB\.DEBUG\] release -> global id=(\d+)"),
    re.compile(r"\[TimescaleDB\.DEBUG\] release -> local id=(\d+)"),
    re.compile(r"\[TimescaleDB\.DEBUG\] release -> unknown/close id=(\d+)"),
    re.compile(r"\[TimescaleDB\.DEBUG\] put_connection called id=(\d+)"),
]

def find_ids(path):
    gets = defaultdict(int)
    puts = defaultdict(int)
    lines = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f, 1):
            lines.append((i, line.rstrip("\n")))
            for xp in GET_PATTERNS:
                m = xp.search(line)
                if m:
                    gets[m.group(1)] += 1
            for xp in PUT_PATTERNS:
                m = xp.search(line)
                if m:
                    puts[m.group(1)] += 1
    return gets, puts, lines

def report(gets, puts):
    all_ids = set(gets) | set(puts)
    leaked = []
    for idv in sorted(all_ids, key=int):
        g = gets.get(idv, 0)
        p = puts.get(idv, 0)
        if g > p:
            leaked.append((idv, g, p))
    return leaked

def main():
    if len(sys.argv) < 2:
        print("Usage: python log_analyze.py logfile.log")
        sys.exit(1)
    path = sys.argv[1]
    gets, puts, _ = find_ids(path)
    leaked = report(gets, puts)
    print("Summary:")
    print(f" total distinct get ids: {len(gets)}")
    print(f" total distinct put ids: {len(puts)}")
    print(f" leaked ids (get > put): {len(leaked)}")
    if leaked:
        print("\nLeaked ids (id, gets, puts):")
        for idv, g, p in leaked:
            print(f" {idv}  gets={g}  puts={p}")
    else:
        print(" No leaked ids detected in this log file (within captured window).")

if __name__ == '__main__':
    main()