"""
Report Generator - Generate HTML/PDF backtest reports
"""

import logging
from typing import Dict, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates backtest reports"""
    
    def __init__(self, output_dir: str = "./reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_html(
        self,
        backtest_results: Dict,
        model_name: str = "Model",
        filename: Optional[str] = None
    ) -> str:
        """
        Generate HTML backtest report
        
        Args:
            backtest_results: Results from strategy.backtester
            model_name: Name of the model
            filename: Optional output filename
            
        Returns:
            Path to generated report
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"backtest_report_{model_name}_{timestamp}.html"
        
        output_path = self.output_dir / filename
        
        # Generate HTML content
        html = self._generate_html_content(backtest_results, model_name)
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.info(f"Generated HTML report: {output_path}")
        
        return str(output_path)
    
    def _generate_html_content(self, results: Dict, model_name: str) -> str:
        """Generate HTML content for report"""
        
        metrics = results.get('metrics', {})
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Backtest Report - {model_name}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
        }}
        .metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .metric-label {{
            font-size: 14px;
            opacity: 0.9;
            margin-bottom: 5px;
        }}
        .metric-value {{
            font-size: 28px;
            font-weight: bold;
        }}
        .positive {{
            color: #4CAF50;
        }}
        .negative {{
            color: #f44336;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #4CAF50;
            color: white;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            text-align: center;
            color: #888;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Backtest Report: {model_name}</h1>
        
        <div class="metrics">
            <div class="metric-card">
                <div class="metric-label">Total Return</div>
                <div class="metric-value {'positive' if results.get('total_return', 0) > 0 else 'negative'}">
                    {results.get('total_return', 0):.2f}%
                </div>
            </div>
            
            <div class="metric-card">
                <div class="metric-label">Sharpe Ratio</div>
                <div class="metric-value">
                    {metrics.get('sharpe_ratio', 0):.2f}
                </div>
            </div>
            
            <div class="metric-card">
                <div class="metric-label">Max Drawdown</div>
                <div class="metric-value negative">
                    {metrics.get('max_drawdown_pct', 0):.2f}%
                </div>
            </div>
            
            <div class="metric-card">
                <div class="metric-label">Number of Trades</div>
                <div class="metric-value">
                    {results.get('n_trades', 0)}
                </div>
            </div>
        </div>
        
        <h2>Prediction Metrics</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>MAE (Mean Absolute Error)</td>
                <td>{metrics.get('MAE', 0):.2f} KRW</td>
            </tr>
            <tr>
                <td>RMSE (Root Mean Squared Error)</td>
                <td>{metrics.get('RMSE', 0):.2f} KRW</td>
            </tr>
            <tr>
                <td>MAPE (Mean Absolute Percentage Error)</td>
                <td>{metrics.get('MAPE', 0):.2f}%</td>
            </tr>
            <tr>
                <td>Direction Accuracy</td>
                <td>{metrics.get('direction_accuracy', 0):.2f}%</td>
            </tr>
        </table>
        
        <h2>Trading Metrics</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>Win Rate</td>
                <td>{metrics.get('win_rate_pct', 0):.2f}%</td>
            </tr>
            <tr>
                <td>Volatility (Annualized)</td>
                <td>{metrics.get('volatility_pct', 0):.2f}%</td>
            </tr>
            <tr>
                <td>Final Equity</td>
                <td>{results.get('final_equity', 0):,.0f} KRW</td>
            </tr>
        </table>
        
        <div class="footer">
            Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </div>
    </div>
</body>
</html>
        """
        
        return html
    
    def generate_summary(self, results: Dict) -> str:
        """
        Generate text summary of results
        
        Args:
            results: Backtest results
            
        Returns:
            Text summary
        """
        metrics = results.get('metrics', {})
        
        summary = f"""
Backtest Summary
================
Period: {results.get('start_date')} to {results.get('end_date')}
Total Return: {results.get('total_return', 0):.2f}%
Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}
Max Drawdown: {metrics.get('max_drawdown_pct', 0):.2f}%
Number of Trades: {results.get('n_trades', 0)}

Prediction Metrics:
  MAE: {metrics.get('MAE', 0):.2f} KRW
  RMSE: {metrics.get('RMSE', 0):.2f} KRW
  MAPE: {metrics.get('MAPE', 0):.2f}%
  Direction Accuracy: {metrics.get('direction_accuracy', 0):.2f}%
        """
        
        return summary.strip()
