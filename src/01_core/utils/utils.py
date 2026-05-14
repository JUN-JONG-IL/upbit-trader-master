"""
[Purpose]
- 공통 유틸리티 모듈: 로깅 설정, 파일/리소스 경로 처리, Windows asyncio 정책 처리, multiprocessing 컨텍스트 설정을 담당

[Responsibilities]
- get_logger(), get_file_path(), ui_path(), style_path(), ...
- set_windows_selector_event_loop_global(), set_multiprocessing_context()
"""

import os
import sys
import logging
import asyncio as aio
from multiprocessing import set_start_method

def _get_src_dir() -> str:
    """
    항상 'src' 폴더의 절대경로만 반환(어떤 위치서 실행해도 동일)
    """
    # 1) frozen/빌드 - 실행파일경로 기준
    if getattr(sys, "frozen", False):
        bindir = os.path.dirname(sys.executable)
        # upbit-trader-master/bin/upbit-trader.exe 이런 경우일 수 있으니, bin이 아니면 src로 추정
        if os.path.basename(bindir).lower() == 'src':
            return bindir
        # bin에서 src상위 탐색
        parent = bindir
        while parent and not os.path.isdir(os.path.join(parent, 'app')):
            prev = parent
            parent = os.path.dirname(parent)
            if parent == prev:
                break
        return parent
    # 2) 평상시(py) - src/utils/의 상위가 src/
    test_path = os.path.abspath(__file__)
    if os.path.basename(os.path.dirname(test_path)).lower() == 'utils':
        return os.path.dirname(os.path.dirname(test_path))
    # 혹시 src 디렉터리 안쪽일 경우
    if os.path.basename(test_path) == 'utils.py':
        return os.path.dirname(os.path.dirname(test_path))
    # 일반적으로 포함 못하면 CWD fallback
    return os.getcwd()

def get_file_path(filename: str):
    """
    src 기준의 절대 경로
    ex) get_file_path("config/config.yaml") → {abspath}/src/config/config.yaml
    """
    src_dir = _get_src_dir()
    return os.path.join(src_dir, filename)

def ui_path(filename: str) -> str:
    """
    항상 src/app/ui/{filename}만 반환
    ex) ui_path("main.ui") → {abspath}/src/app/ui/main.ui
    """
    return get_file_path(os.path.join("app", "ui", filename))

def style_path(relpath: str) -> str:
    """
    src/styles/ 하위 리소스 반환
    ex) style_path("dark/branch_closed.svg") → {abspath}/src/styles/dark/branch_closed.svg
    """
    return get_file_path(os.path.join("styles", relpath))

def get_logger(
    print_format: str = '[%(asctime)s.%(msecs)03d: %(levelname).1s %(filename)s:%(lineno)s] %(message)s',
    date_format: str = '%Y-%m-%d %H:%M:%S',
    print: bool = True,
    save: bool = True,
    save_path: str = 'upbit-trader.log'
):
    log = logging.getLogger()
    log.setLevel(logging.INFO)
    formatter = logging.Formatter(fmt=print_format, datefmt=date_format)
    if print:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        log.addHandler(stream_handler)
    if save:
        if save_path == 'upbit-trader.log' and not sys.platform.startswith('win'):
            file_handler = logging.FileHandler('upbit-trader.log')
        else:
            file_handler = logging.FileHandler(save_path)
        file_handler.setFormatter(formatter)
        log.addHandler(file_handler)
    return log

def set_windows_selector_event_loop_global():
    py_ver = int(f"{sys.version_info.major}{sys.version_info.minor}")
    if py_ver > 37 and sys.platform.startswith('win'):
        aio.set_event_loop_policy(aio.WindowsSelectorEventLoopPolicy())

def set_multiprocessing_context():
    if sys.platform == 'darwin' and getattr(sys, "frozen", False):
        set_start_method('fork')