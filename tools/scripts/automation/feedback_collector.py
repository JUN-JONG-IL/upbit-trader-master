#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
사용자 피드백 루프 (Feedback Collector)

[Purpose]
사용자 피드백 수집, 분석, GitHub Issues 자동 생성을 제공합니다.

[Responsibilities]
- 작업 후 자동 설문/로그 수집
- GitHub Issues 자동 생성 (문제 발견 시)
- 사용자 지시서 자동 해석 개선
- 개선 사항 자동 제안

[Main Flow]
1. 사용자 피드백 수집
2. 피드백 분석 (패턴 인식)
3. 문제 발견 시 Issue 생성
4. 개선 제안 생성

[Dependencies]
- Python 표준 라이브러리

[Author] Copilot
[Created] 2026-02-03
[Modified] 2026-02-03
"""

import os
import sys
import json
import datetime
import argparse
from pathlib import Path
from typing import Dict, List, Optional


class FeedbackCollector:
    """피드백 수집 및 분석 클래스"""
    
    def __init__(self, repo_root: Path):
        """
        초기화
        
        Args:
            repo_root: 레포지토리 루트 경로
        """
        self.repo_root = repo_root
        self.feedback_dir = repo_root / 'feedback'
        self.feedback_dir.mkdir(exist_ok=True)
        
        self.feedback_file = self.feedback_dir / 'feedback_log.jsonl'
    
    def collect_feedback(
        self,
        task: str,
        rating: int,
        comment: Optional[str] = None,
        issues: Optional[List[str]] = None
    ) -> bool:
        """
        피드백 수집
        
        Args:
            task: 작업 이름
            rating: 평점 (1-5)
            comment: 코멘트
            issues: 발견된 문제 목록
        
        Returns:
            bool: 수집 성공 여부
        """
        if not 1 <= rating <= 5:
            print("❌ 평점은 1-5 사이여야 합니다")
            return False
        
        feedback = {
            'timestamp': datetime.datetime.now().isoformat(),
            'task': task,
            'rating': rating,
            'comment': comment or '',
            'issues': issues or []
        }
        
        # JSONL 형식으로 저장
        with open(self.feedback_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(feedback, ensure_ascii=False) + '\n')
        
        print(f"✅ 피드백 수집 완료: {task} (평점: {rating}/5)")
        return True
    
    def analyze_feedback(self) -> Dict:
        """
        피드백 분석
        
        Returns:
            Dict: 분석 결과
        """
        print("\n=== 📊 피드백 분석 ===\n")
        
        if not self.feedback_file.exists():
            print("수집된 피드백이 없습니다")
            return {
                'total': 0,
                'average_rating': 0,
                'common_issues': []
            }
        
        feedbacks = []
        with open(self.feedback_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    feedbacks.append(json.loads(line))
        
        if not feedbacks:
            print("수집된 피드백이 없습니다")
            return {
                'total': 0,
                'average_rating': 0,
                'common_issues': []
            }
        
        # 평균 평점 계산
        total_rating = sum(f['rating'] for f in feedbacks)
        average_rating = total_rating / len(feedbacks)
        
        # 공통 이슈 추출
        all_issues = []
        for f in feedbacks:
            all_issues.extend(f.get('issues', []))
        
        # 이슈 빈도 계산
        from collections import Counter
        issue_counter = Counter(all_issues)
        common_issues = issue_counter.most_common(10)
        
        # 최근 피드백
        recent_feedbacks = feedbacks[-5:]
        
        print(f"전체 피드백 수: {len(feedbacks)}")
        print(f"평균 평점: {average_rating:.2f}/5.0")
        
        if common_issues:
            print(f"\n공통 이슈 (상위 5개):")
            for issue, count in common_issues[:5]:
                print(f"  - {issue} ({count}회)")
        
        print(f"\n최근 피드백 (5개):")
        for fb in recent_feedbacks:
            print(f"  [{fb['timestamp'][:10]}] {fb['task']}: {fb['rating']}/5")
            if fb['comment']:
                print(f"    → {fb['comment']}")
        
        return {
            'total': len(feedbacks),
            'average_rating': average_rating,
            'common_issues': common_issues,
            'recent_feedbacks': recent_feedbacks
        }
    
    def create_issue(
        self,
        title: str,
        description: str,
        labels: Optional[List[str]] = None
    ) -> bool:
        """
        GitHub Issue 템플릿 생성
        
        Args:
            title: 이슈 제목
            description: 이슈 설명
            labels: 라벨 목록
        
        Returns:
            bool: 생성 성공 여부
        """
        print("\n=== 🐛 GitHub Issue 템플릿 생성 ===\n")
        
        # Issue 파일 생성
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        issue_file = self.feedback_dir / f'issue_{timestamp}.md'
        
        labels_str = ', '.join(labels) if labels else 'bug'
        
        issue_content = f"""# {title}

**라벨**: {labels_str}
**생성일**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 설명

{description}

## 재현 방법

1. 
2. 
3. 

## 예상 동작

[예상 동작 설명]

## 실제 동작

[실제 동작 설명]

## 환경

- OS: 
- Python: {sys.version}
- 기타: 

## 추가 정보

[추가 정보 또는 스크린샷]

---
*이 이슈는 automation/feedback_collector.py에 의해 자동 생성되었습니다.*
"""
        
        with open(issue_file, 'w', encoding='utf-8') as f:
            f.write(issue_content)
        
        print(f"✅ Issue 템플릿 생성: {issue_file}")
        print(f"\n다음 명령으로 GitHub에 이슈를 생성하세요:")
        print(f"  gh issue create --title \"{title}\" --body-file {issue_file}")
        
        return True
    
    def suggest_improvements(self, analysis: Dict) -> List[str]:
        """
        개선 사항 제안
        
        Args:
            analysis: 피드백 분석 결과
        
        Returns:
            List[str]: 개선 제안 목록
        """
        print("\n=== 💡 개선 제안 ===\n")
        
        suggestions = []
        
        # 평균 평점 기반 제안
        avg_rating = analysis.get('average_rating', 0)
        if avg_rating < 3.0:
            suggestions.append("전체적인 만족도가 낮습니다. 주요 문제점을 파악하고 개선하세요.")
        elif avg_rating < 4.0:
            suggestions.append("만족도가 보통입니다. 사용자 경험 개선이 필요합니다.")
        else:
            suggestions.append("만족도가 높습니다. 현재 수준을 유지하세요.")
        
        # 공통 이슈 기반 제안
        common_issues = analysis.get('common_issues', [])
        if common_issues:
            top_issue = common_issues[0]
            suggestions.append(f"가장 빈번한 이슈: '{top_issue[0]}' ({top_issue[1]}회)")
            suggestions.append(f"  → 이 문제를 우선적으로 해결하세요.")
        
        # 피드백 수 기반 제안
        total = analysis.get('total', 0)
        if total < 10:
            suggestions.append("피드백이 부족합니다. 더 많은 피드백을 수집하세요.")
        
        for i, suggestion in enumerate(suggestions, 1):
            print(f"{i}. {suggestion}")
        
        return suggestions
    
    def interactive_feedback(self, task: str):
        """
        대화형 피드백 수집
        
        Args:
            task: 작업 이름
        """
        print(f"\n=== 📝 피드백 수집: {task} ===\n")
        
        # 평점 입력
        while True:
            try:
                rating = int(input("평점을 입력하세요 (1-5): "))
                if 1 <= rating <= 5:
                    break
                print("1-5 사이의 숫자를 입력하세요")
            except ValueError:
                print("숫자를 입력하세요")
        
        # 코멘트 입력
        comment = input("코멘트 (선택, Enter로 건너뛰기): ").strip()
        
        # 이슈 입력
        issues = []
        print("\n발견된 문제를 입력하세요 (빈 줄로 종료):")
        while True:
            issue = input("  - ").strip()
            if not issue:
                break
            issues.append(issue)
        
        # 피드백 저장
        self.collect_feedback(
            task=task,
            rating=rating,
            comment=comment if comment else None,
            issues=issues if issues else None
        )
        
        print("\n✅ 피드백이 저장되었습니다. 감사합니다!")


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description='사용자 피드백 루프',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 대화형 피드백 수집
  python automation/feedback_collector.py --collect --task "자동화 스크립트 실행"
  
  # 피드백 분석
  python automation/feedback_collector.py --analyze
  
  # GitHub Issue 생성
  python automation/feedback_collector.py --create-issue \\
    --title "버그: 테스트 실패" \\
    --description "테스트가 간헐적으로 실패합니다"
  
  # 개선 제안
  python automation/feedback_collector.py --suggest
        """
    )
    
    parser.add_argument(
        '--collect',
        action='store_true',
        help='피드백 수집 (대화형)'
    )
    
    parser.add_argument(
        '--task',
        help='작업 이름'
    )
    
    parser.add_argument(
        '--analyze',
        action='store_true',
        help='피드백 분석'
    )
    
    parser.add_argument(
        '--create-issue',
        action='store_true',
        help='GitHub Issue 템플릿 생성'
    )
    
    parser.add_argument(
        '--title',
        help='이슈 제목'
    )
    
    parser.add_argument(
        '--description',
        help='이슈 설명'
    )
    
    parser.add_argument(
        '--suggest',
        action='store_true',
        help='개선 제안'
    )
    
    args = parser.parse_args()
    
    # 레포지토리 루트 찾기
    repo_root = Path(__file__).parent.parent
    collector = FeedbackCollector(repo_root)
    
    if args.collect:
        if not args.task:
            print("❌ --task 옵션이 필요합니다")
            sys.exit(1)
        
        collector.interactive_feedback(args.task)
    
    elif args.analyze or args.suggest:
        analysis = collector.analyze_feedback()
        
        if args.suggest:
            collector.suggest_improvements(analysis)
    
    elif args.create_issue:
        if not args.title or not args.description:
            print("❌ --title 및 --description 옵션이 필요합니다")
            sys.exit(1)
        
        collector.create_issue(args.title, args.description)
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
