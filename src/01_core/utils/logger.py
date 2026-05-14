"""
[Purpose]
JSON 구조화 로깅 시스템

[Responsibilities]
- JSON 형식 로그 출력
- 파일 로테이션 (일별, 크기 기반)
- 레벨별 출력 (콘솔 ERROR, 파일 INFO)

[Main Flow]
1. 로거 설정 (JSON 포맷, 로테이션)
2. 로그 기록 (timestamp, level, module, message 등)
3. 자동 로테이션 (10MB 또는 일별)
"""

import logging
import json
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JsonFormatter(logging.Formatter):
    """JSON 형식 로그 포맷터"""
    
    def format(self, record):
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage()
        }
        
        # 추가 필드
        if hasattr(record, 'exchange'):
            log_data['exchange'] = record.exchange
        if hasattr(record, 'symbol'):
            log_data['symbol'] = record.symbol
        if hasattr(record, 'latency_ms'):
            log_data['latency_ms'] = record.latency_ms
        
        # 예외 정보
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


def setup_logger(
    name: str = "upbit_trader",
    log_dir: str = "logs",
    console_level: int = logging.ERROR,
    file_level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 7
) -> logging.Logger:
    """
    로거 설정
    
    Args:
        name: 로거 이름
        log_dir: 로그 파일 디렉토리
        console_level: 콘솔 출력 레벨
        file_level: 파일 출력 레벨
        max_bytes: 파일 최대 크기
        backup_count: 보관 파일 수
    
    Returns:
        설정된 로거
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    
    # 로그 디렉토리 생성
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 파일 핸들러 (JSON)
    log_file = log_path / f"upbit-trader-{datetime.now().strftime('%Y-%m-%d')}.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)
    
    return logger


# 전역 로거
logger = setup_logger()
