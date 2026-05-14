#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Social Media Influence Score Module

소셜 미디어 영향력 점수를 계산합니다.
- 팔로워 수 기반 가중치
- Retweet 전파 계수 (Virality Score)
- 검증된 계정 부스팅
"""

import logging
from typing import Dict, List, Optional
import numpy as np

logger = logging.getLogger(__name__)


class InfluenceScoreCalculator:
    """
    소셜 미디어 영향력 점수 계산기
    """
    
    def __init__(
        self,
        follower_weight: float = 0.4,
        virality_weight: float = 0.3,
        verified_weight: float = 0.2,
        engagement_weight: float = 0.1
    ):
        """
        Initialize Influence Score Calculator
        
        Args:
            follower_weight: 팔로워 수 가중치
            virality_weight: 전파력 가중치
            verified_weight: 검증 계정 가중치
            engagement_weight: 참여도 가중치
        """
        self.follower_weight = follower_weight
        self.virality_weight = virality_weight
        self.verified_weight = verified_weight
        self.engagement_weight = engagement_weight
        
        # Normalization constants
        self.max_followers = 1_000_000  # Normalize to 1M followers
        self.verified_boost = 1.5  # 검증 계정 1.5배 부스트
        
        logger.info("Influence Score Calculator initialized")
    
    def calculate_influence_score(
        self,
        followers_count: int,
        retweet_count: int = 0,
        like_count: int = 0,
        reply_count: int = 0,
        is_verified: bool = False,
        original_tweet: bool = True
    ) -> Dict:
        """
        영향력 점수 계산
        
        Args:
            followers_count: 팔로워 수
            retweet_count: 리트윗 수
            like_count: 좋아요 수
            reply_count: 답글 수
            is_verified: 검증된 계정 여부
            original_tweet: 원본 트윗 여부
        
        Returns:
            영향력 점수 및 세부 정보
        """
        try:
            # 1. Follower score (normalized)
            follower_score = min(followers_count / self.max_followers, 1.0)
            
            # 2. Virality score (retweet propagation)
            if original_tweet:
                virality_score = self._calculate_virality_score(
                    retweet_count,
                    followers_count
                )
            else:
                virality_score = 0.0  # Retweets don't get virality credit
            
            # 3. Engagement score (likes + replies)
            engagement_score = self._calculate_engagement_score(
                like_count,
                reply_count,
                followers_count
            )
            
            # 4. Verified account boost
            verified_score = 1.0 if is_verified else 0.0
            
            # Calculate weighted total score
            base_score = (
                follower_score * self.follower_weight +
                virality_score * self.virality_weight +
                engagement_score * self.engagement_weight +
                verified_score * self.verified_weight
            )
            
            # Apply verified boost
            if is_verified:
                final_score = base_score * self.verified_boost
            else:
                final_score = base_score
            
            # Normalize to [0, 1]
            final_score = min(final_score, 1.0)
            
            # Calculate tier
            tier = self._get_influence_tier(final_score)
            
            result = {
                'influence_score': float(final_score),
                'tier': tier,
                'components': {
                    'follower_score': float(follower_score),
                    'virality_score': float(virality_score),
                    'engagement_score': float(engagement_score),
                    'verified_score': float(verified_score)
                },
                'is_verified': is_verified,
                'followers_count': followers_count,
                'total_interactions': retweet_count + like_count + reply_count
            }
            
            logger.info(f"Influence score calculated: {final_score:.3f} ({tier})")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to calculate influence score: {e}")
            return {
                'influence_score': 0.0,
                'tier': 'Unknown',
                'components': {},
                'is_verified': False,
                'followers_count': 0
            }
    
    def _calculate_virality_score(
        self,
        retweet_count: int,
        followers_count: int
    ) -> float:
        """
        전파력 점수 계산
        
        Virality = retweets / (followers / 100)
        
        Args:
            retweet_count: 리트윗 수
            followers_count: 팔로워 수
        
        Returns:
            전파력 점수 (0-1)
        """
        if followers_count == 0:
            return 0.0
        
        # Expected retweets based on follower count (assume 1% engagement)
        expected_retweets = followers_count * 0.01
        
        if expected_retweets == 0:
            expected_retweets = 1
        
        # Virality coefficient
        virality = retweet_count / expected_retweets
        
        # Normalize using log scale (to handle viral posts)
        virality_score = np.log1p(virality) / np.log1p(100)  # Max at 100x expected
        
        return min(virality_score, 1.0)
    
    def _calculate_engagement_score(
        self,
        like_count: int,
        reply_count: int,
        followers_count: int
    ) -> float:
        """
        참여도 점수 계산
        
        Args:
            like_count: 좋아요 수
            reply_count: 답글 수
            followers_count: 팔로워 수
        
        Returns:
            참여도 점수 (0-1)
        """
        if followers_count == 0:
            return 0.0
        
        # Total engagement
        total_engagement = like_count + reply_count * 2  # Replies worth more
        
        # Expected engagement (assume 2% engagement rate)
        expected_engagement = followers_count * 0.02
        
        if expected_engagement == 0:
            expected_engagement = 1
        
        # Engagement rate
        engagement_rate = total_engagement / expected_engagement
        
        # Normalize
        engagement_score = np.log1p(engagement_rate) / np.log1p(10)  # Max at 10x expected
        
        return min(engagement_score, 1.0)
    
    def _get_influence_tier(self, score: float) -> str:
        """영향력 등급 결정"""
        if score >= 0.8:
            return "Mega Influencer"
        elif score >= 0.6:
            return "Macro Influencer"
        elif score >= 0.4:
            return "Micro Influencer"
        elif score >= 0.2:
            return "Nano Influencer"
        else:
            return "Regular User"
    
    def calculate_weighted_sentiment(
        self,
        sentiments: List[float],
        influence_scores: List[float]
    ) -> Dict:
        """
        영향력 가중 감성 점수 계산
        
        Args:
            sentiments: 감성 점수 리스트
            influence_scores: 영향력 점수 리스트
        
        Returns:
            가중 감성 점수
        """
        try:
            if len(sentiments) != len(influence_scores):
                logger.error("Sentiments and influence scores must have same length")
                return {
                    'weighted_sentiment': 0.0,
                    'unweighted_sentiment': 0.0
                }
            
            if len(sentiments) == 0:
                return {
                    'weighted_sentiment': 0.0,
                    'unweighted_sentiment': 0.0
                }
            
            sentiments = np.array(sentiments)
            influence_scores = np.array(influence_scores)
            
            # Normalize influence scores
            total_influence = np.sum(influence_scores)
            if total_influence == 0:
                weights = np.ones(len(sentiments)) / len(sentiments)
            else:
                weights = influence_scores / total_influence
            
            # Calculate weighted sentiment
            weighted_sentiment = np.sum(sentiments * weights)
            
            # Calculate unweighted sentiment for comparison
            unweighted_sentiment = np.mean(sentiments)
            
            # Calculate difference
            difference = weighted_sentiment - unweighted_sentiment
            
            result = {
                'weighted_sentiment': float(weighted_sentiment),
                'unweighted_sentiment': float(unweighted_sentiment),
                'difference': float(difference),
                'interpretation': self._interpret_weighting_effect(difference)
            }
            
            logger.info(f"Weighted sentiment: {weighted_sentiment:.3f} (vs {unweighted_sentiment:.3f})")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to calculate weighted sentiment: {e}")
            return {
                'weighted_sentiment': 0.0,
                'unweighted_sentiment': 0.0,
                'difference': 0.0
            }
    
    def _interpret_weighting_effect(self, difference: float) -> str:
        """가중치 효과 해석"""
        if abs(difference) < 0.05:
            return "영향력 가중치 효과 미미"
        elif difference > 0:
            return f"인플루언서들이 더 긍정적 (차이: +{difference:.3f})"
        else:
            return f"인플루언서들이 더 부정적 (차이: {difference:.3f})"
    
    def rank_influencers(
        self,
        user_data: List[Dict]
    ) -> List[Dict]:
        """
        인플루언서 순위 매기기
        
        Args:
            user_data: 사용자 데이터 리스트
                각 dict는 followers_count, retweet_count 등 포함
        
        Returns:
            영향력 순으로 정렬된 사용자 리스트
        """
        try:
            # Calculate influence score for each user
            for user in user_data:
                score_result = self.calculate_influence_score(
                    followers_count=user.get('followers_count', 0),
                    retweet_count=user.get('retweet_count', 0),
                    like_count=user.get('like_count', 0),
                    reply_count=user.get('reply_count', 0),
                    is_verified=user.get('is_verified', False),
                    original_tweet=user.get('original_tweet', True)
                )
                
                user['influence_score'] = score_result['influence_score']
                user['influence_tier'] = score_result['tier']
            
            # Sort by influence score (descending)
            ranked_users = sorted(
                user_data,
                key=lambda x: x.get('influence_score', 0),
                reverse=True
            )
            
            logger.info(f"Ranked {len(ranked_users)} users by influence")
            
            return ranked_users
            
        except Exception as e:
            logger.error(f"Failed to rank influencers: {e}")
            return user_data


def calculate_social_influence(
    followers_count: int,
    retweet_count: int = 0,
    like_count: int = 0,
    is_verified: bool = False
) -> Dict:
    """
    Convenience function for influence score calculation
    
    Args:
        followers_count: 팔로워 수
        retweet_count: 리트윗 수
        like_count: 좋아요 수
        is_verified: 검증 계정 여부
    
    Returns:
        영향력 점수
    """
    calculator = InfluenceScoreCalculator()
    return calculator.calculate_influence_score(
        followers_count,
        retweet_count,
        like_count,
        is_verified=is_verified
    )


if __name__ == "__main__":
    """테스트 실행"""
    calculator = InfluenceScoreCalculator()
    
    # Test cases
    test_users = [
        {
            'name': 'Mega Influencer',
            'followers_count': 1_000_000,
            'retweet_count': 5000,
            'like_count': 20000,
            'reply_count': 500,
            'is_verified': True,
            'original_tweet': True
        },
        {
            'name': 'Micro Influencer',
            'followers_count': 10_000,
            'retweet_count': 50,
            'like_count': 200,
            'reply_count': 20,
            'is_verified': False,
            'original_tweet': True
        },
        {
            'name': 'Regular User',
            'followers_count': 500,
            'retweet_count': 2,
            'like_count': 10,
            'reply_count': 1,
            'is_verified': False,
            'original_tweet': True
        }
    ]
    
    print("Influence Score Test Results:")
    for user in test_users:
        result = calculator.calculate_influence_score(**user)
        print(f"\n{user['name']}:")
        print(f"  Score: {result['influence_score']:.3f}")
        print(f"  Tier: {result['tier']}")
        print(f"  Components: {result['components']}")
