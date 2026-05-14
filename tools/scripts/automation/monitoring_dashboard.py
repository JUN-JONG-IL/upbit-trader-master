#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
실시간 모니터링 대시보드 (Monitoring Dashboard)

[Purpose]
트레이딩 시스템의 상태를 실시간으로 모니터링하고 시각화합니다.

[Responsibilities]
- 시스템 상태 실시간 모니터링
- 알림 시스템 (콘솔 출력)
- 성능 메트릭 수집 및 표시
- 오류 즉시 보고

[Main Flow]
1. 시스템 메트릭 수집 (CPU, 메모리, 디스크)
2. 서비스 상태 확인 (Docker, MongoDB, Redis, Kafka)
3. 웹 인터페이스로 실시간 표시
4. 임계값 초과 시 알림

[Dependencies]
- flask: 웹 대시보드 (optional)
- streamlit: 대시보드 UI (optional)
- psutil: 시스템 메트릭

[Author] Copilot
[Created] 2026-02-03
[Modified] 2026-02-03
"""

import os
import sys
import time
import json
import argparse
import subprocess
import datetime
from pathlib import Path
from typing import Dict, List, Optional
from collections import deque

# Optional dependencies
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("⚠️  psutil이 설치되지 않았습니다. 시스템 메트릭을 수집할 수 없습니다.")
    print("   설치하려면: pip install psutil")

try:
    from flask import Flask, jsonify, render_template_string
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    Flask = None  # Define Flask as None when not available


class SystemMonitor:
    """시스템 모니터링 클래스"""
    
    def __init__(self, repo_root: Path):
        """
        초기화
        
        Args:
            repo_root: 레포지토리 루트 경로
        """
        self.repo_root = repo_root
        self.history = {
            'cpu': deque(maxlen=100),
            'memory': deque(maxlen=100),
            'disk': deque(maxlen=100),
            'timestamps': deque(maxlen=100)
        }
        
        # 임계값 설정
        self.thresholds = {
            'cpu': 80.0,      # CPU 사용률 80% 이상
            'memory': 85.0,   # 메모리 사용률 85% 이상
            'disk': 90.0      # 디스크 사용률 90% 이상
        }
    
    def get_system_metrics(self) -> Dict:
        """
        시스템 메트릭 수집
        
        Returns:
            Dict: 시스템 메트릭
        """
        if not PSUTIL_AVAILABLE:
            return {
                'cpu_percent': 0.0,
                'memory_percent': 0.0,
                'disk_percent': 0.0,
                'error': 'psutil not available'
            }
        
        metrics = {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage('/').percent,
            'timestamp': datetime.datetime.now().isoformat()
        }
        
        # 히스토리에 추가
        self.history['cpu'].append(metrics['cpu_percent'])
        self.history['memory'].append(metrics['memory_percent'])
        self.history['disk'].append(metrics['disk_percent'])
        self.history['timestamps'].append(metrics['timestamp'])
        
        return metrics
    
    def check_docker_services(self) -> Dict:
        """
        Docker 서비스 상태 확인
        
        Returns:
            Dict: 서비스 상태
        """
        services = {
            'docker': False,
            'mongodb': False,
            'redis': False,
            'kafka': False
        }
        
        # Docker 데몬 확인
        try:
            result = subprocess.run(
                ['docker', 'info'],
                capture_output=True,
                timeout=5
            )
            services['docker'] = result.returncode == 0
        except:
            pass
        
        # Docker Compose 서비스 확인
        if services['docker']:
            try:
                result = subprocess.run(
                    ['docker-compose', 'ps'],
                    capture_output=True,
                    text=True,
                    cwd=self.repo_root,
                    timeout=10
                )
                
                output = result.stdout.lower()
                services['mongodb'] = 'mongodb' in output and 'up' in output
                services['redis'] = 'redis' in output and 'up' in output
                services['kafka'] = 'kafka' in output and 'up' in output
            except:
                pass
        
        return services
    
    def check_health(self) -> Dict:
        """
        전체 시스템 상태 확인
        
        Returns:
            Dict: 상태 정보
        """
        metrics = self.get_system_metrics()
        services = self.check_docker_services()
        
        # 알림 확인
        alerts = []
        if metrics.get('cpu_percent', 0) > self.thresholds['cpu']:
            alerts.append(f"⚠️  CPU 사용률 높음: {metrics['cpu_percent']:.1f}%")
        
        if metrics.get('memory_percent', 0) > self.thresholds['memory']:
            alerts.append(f"⚠️  메모리 사용률 높음: {metrics['memory_percent']:.1f}%")
        
        if metrics.get('disk_percent', 0) > self.thresholds['disk']:
            alerts.append(f"⚠️  디스크 사용률 높음: {metrics['disk_percent']:.1f}%")
        
        if not services.get('docker'):
            alerts.append("❌ Docker가 실행 중이지 않습니다")
        
        if services.get('docker') and not services.get('mongodb'):
            alerts.append("⚠️  MongoDB 서비스가 실행 중이지 않습니다")
        
        if services.get('docker') and not services.get('redis'):
            alerts.append("⚠️  Redis 서비스가 실행 중이지 않습니다")
        
        return {
            'metrics': metrics,
            'services': services,
            'alerts': alerts,
            'status': 'healthy' if not alerts else 'warning'
        }
    
    def print_status(self, health: Dict):
        """
        상태를 콘솔에 출력
        
        Args:
            health: 상태 정보
        """
        print("\n" + "="*60)
        print(f"🖥️  시스템 모니터링 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        # 시스템 메트릭
        metrics = health['metrics']
        print("\n📊 시스템 메트릭:")
        print(f"  CPU 사용률:    {metrics.get('cpu_percent', 0):6.1f}%")
        print(f"  메모리 사용률: {metrics.get('memory_percent', 0):6.1f}%")
        print(f"  디스크 사용률: {metrics.get('disk_percent', 0):6.1f}%")
        
        # 서비스 상태
        services = health['services']
        print("\n🔧 서비스 상태:")
        print(f"  Docker:   {'✅ 실행 중' if services['docker'] else '❌ 중지됨'}")
        print(f"  MongoDB:  {'✅ 실행 중' if services['mongodb'] else '❌ 중지됨'}")
        print(f"  Redis:    {'✅ 실행 중' if services['redis'] else '❌ 중지됨'}")
        print(f"  Kafka:    {'✅ 실행 중' if services['kafka'] else '❌ 중지됨'}")
        
        # 알림
        if health['alerts']:
            print("\n⚠️  경고:")
            for alert in health['alerts']:
                print(f"  {alert}")
        else:
            print("\n✅ 모든 시스템이 정상입니다")
        
        print("\n" + "="*60)


def create_flask_app(monitor: SystemMonitor):
    """
    Flask 웹 대시보드 생성
    
    Args:
        monitor: SystemMonitor 인스턴스
    
    Returns:
        Flask app or None if Flask not available
    """
    if not FLASK_AVAILABLE:
        return None
    
    app = Flask(__name__)
    
    # 간단한 HTML 템플릿
    DASHBOARD_HTML = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Upbit Trader 모니터링</title>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="5">
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 {
                color: #333;
                border-bottom: 3px solid #007bff;
                padding-bottom: 10px;
            }
            .metrics {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin: 20px 0;
            }
            .metric-card {
                background: #f8f9fa;
                padding: 20px;
                border-radius: 8px;
                border-left: 4px solid #007bff;
            }
            .metric-value {
                font-size: 32px;
                font-weight: bold;
                color: #007bff;
            }
            .metric-label {
                font-size: 14px;
                color: #666;
                margin-top: 5px;
            }
            .services {
                margin: 20px 0;
            }
            .service-item {
                padding: 10px;
                margin: 5px 0;
                background: #f8f9fa;
                border-radius: 5px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .status-ok {
                color: #28a745;
                font-weight: bold;
            }
            .status-error {
                color: #dc3545;
                font-weight: bold;
            }
            .alerts {
                margin: 20px 0;
            }
            .alert {
                padding: 15px;
                margin: 10px 0;
                background: #fff3cd;
                border-left: 4px solid #ffc107;
                border-radius: 5px;
            }
            .timestamp {
                color: #666;
                font-size: 12px;
                text-align: right;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Upbit Trader 실시간 모니터링</h1>
            
            <div class="timestamp">마지막 업데이트: {{ timestamp }}</div>
            
            <h2>📊 시스템 메트릭</h2>
            <div class="metrics">
                <div class="metric-card">
                    <div class="metric-value">{{ cpu }}%</div>
                    <div class="metric-label">CPU 사용률</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{{ memory }}%</div>
                    <div class="metric-label">메모리 사용률</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{{ disk }}%</div>
                    <div class="metric-label">디스크 사용률</div>
                </div>
            </div>
            
            <h2>🔧 서비스 상태</h2>
            <div class="services">
                <div class="service-item">
                    <span>Docker</span>
                    <span class="{{ docker_class }}">{{ docker_status }}</span>
                </div>
                <div class="service-item">
                    <span>MongoDB</span>
                    <span class="{{ mongodb_class }}">{{ mongodb_status }}</span>
                </div>
                <div class="service-item">
                    <span>Redis</span>
                    <span class="{{ redis_class }}">{{ redis_status }}</span>
                </div>
                <div class="service-item">
                    <span>Kafka</span>
                    <span class="{{ kafka_class }}">{{ kafka_status }}</span>
                </div>
            </div>
            
            {% if alerts %}
            <h2>⚠️ 경고</h2>
            <div class="alerts">
                {% for alert in alerts %}
                <div class="alert">{{ alert }}</div>
                {% endfor %}
            </div>
            {% endif %}
            
            <p style="margin-top: 30px; color: #666; font-size: 12px;">
                * 페이지는 5초마다 자동으로 새로고침됩니다.
            </p>
        </div>
    </body>
    </html>
    """
    
    @app.route('/')
    def dashboard():
        """대시보드 페이지"""
        health = monitor.check_health()
        metrics = health['metrics']
        services = health['services']
        
        return render_template_string(
            DASHBOARD_HTML,
            timestamp=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            cpu=f"{metrics.get('cpu_percent', 0):.1f}",
            memory=f"{metrics.get('memory_percent', 0):.1f}",
            disk=f"{metrics.get('disk_percent', 0):.1f}",
            docker_status='✅ 실행 중' if services['docker'] else '❌ 중지됨',
            docker_class='status-ok' if services['docker'] else 'status-error',
            mongodb_status='✅ 실행 중' if services['mongodb'] else '❌ 중지됨',
            mongodb_class='status-ok' if services['mongodb'] else 'status-error',
            redis_status='✅ 실행 중' if services['redis'] else '❌ 중지됨',
            redis_class='status-ok' if services['redis'] else 'status-error',
            kafka_status='✅ 실행 중' if services['kafka'] else '❌ 중지됨',
            kafka_class='status-ok' if services['kafka'] else 'status-error',
            alerts=health['alerts']
        )
    
    @app.route('/api/health')
    def api_health():
        """Health API 엔드포인트"""
        return jsonify(monitor.check_health())
    
    return app


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description='실시간 모니터링 대시보드',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 콘솔 모니터링 (1회)
  python automation/monitoring_dashboard.py
  
  # 콘솔 모니터링 (지속)
  python automation/monitoring_dashboard.py --watch
  
  # 웹 대시보드 시작 (Flask)
  python automation/monitoring_dashboard.py --web --port 5000
  
  # JSON 출력
  python automation/monitoring_dashboard.py --json
        """
    )
    
    parser.add_argument(
        '--watch',
        action='store_true',
        help='지속적으로 모니터링 (Ctrl+C로 종료)'
    )
    
    parser.add_argument(
        '--web',
        action='store_true',
        help='웹 대시보드 시작 (Flask 필요)'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=5000,
        help='웹 서버 포트 (기본값: 5000)'
    )
    
    parser.add_argument(
        '--interval',
        type=int,
        default=5,
        help='모니터링 간격 (초, 기본값: 5)'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='JSON 형식으로 출력'
    )
    
    args = parser.parse_args()
    
    # 레포지토리 루트 찾기
    repo_root = Path(__file__).parent.parent
    monitor = SystemMonitor(repo_root)
    
    if args.web:
        if not FLASK_AVAILABLE:
            print("❌ Flask가 설치되지 않았습니다.")
            print("   설치하려면: pip install flask")
            sys.exit(1)
        
        print(f"\n🌐 웹 대시보드 시작: http://localhost:{args.port}")
        print("   Ctrl+C로 종료\n")
        
        app = create_flask_app(monitor)
        app.run(host='0.0.0.0', port=args.port, debug=False)
    
    elif args.watch:
        print("\n📊 실시간 모니터링 시작 (Ctrl+C로 종료)\n")
        
        try:
            while True:
                health = monitor.check_health()
                
                if args.json:
                    print(json.dumps(health, indent=2, ensure_ascii=False))
                else:
                    monitor.print_status(health)
                
                time.sleep(args.interval)
        
        except KeyboardInterrupt:
            print("\n\n✅ 모니터링 종료")
    
    else:
        # 1회 실행
        health = monitor.check_health()
        
        if args.json:
            print(json.dumps(health, indent=2, ensure_ascii=False))
        else:
            monitor.print_status(health)


if __name__ == '__main__':
    main()
