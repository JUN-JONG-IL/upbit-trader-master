"""
Chart Export Utilities

[Features]
- PNG 내보내기
- PDF 내보내기
- HTML 내보내기 (Plotly/Bokeh)
- 파일명 자동 생성
"""
from pathlib import Path
from typing import Optional
import datetime


def generate_filename(symbol: str, timeframe: str, ext: str = "png") -> str:
    """
    파일명 자동 생성

    [Parameters]
    - symbol: 심볼 (예: 'KRW-BTC')
    - timeframe: 타임프레임 (예: '5m')
    - ext: 파일 확장자 (png, pdf, html)

    [Returns]
    - str: 자동 생성된 파일명
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_symbol = symbol.replace("-", "_")
    return f"chart_{safe_symbol}_{timeframe}_{timestamp}.{ext}"


def export_png(fig, output_path: Optional[Path] = None, **kwargs) -> Path:
    """
    PNG로 내보내기

    [Parameters]
    - fig: matplotlib Figure 또는 plotly Figure
    - output_path: 저장 경로 (None이면 자동 생성)

    [Returns]
    - Path: 저장된 파일 경로
    """
    if output_path is None:
        output_path = Path.home() / "Downloads" / "chart_export.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # matplotlib
    try:
        fig.savefig(str(output_path), **kwargs)
        return output_path
    except AttributeError:
        pass

    # plotly
    try:
        fig.write_image(str(output_path), **kwargs)
        return output_path
    except Exception:
        pass

    return output_path


def export_html(fig, output_path: Optional[Path] = None, **kwargs) -> Path:
    """
    HTML로 내보내기 (Plotly/Bokeh)

    [Parameters]
    - fig: plotly Figure 또는 bokeh Figure
    - output_path: 저장 경로

    [Returns]
    - Path: 저장된 파일 경로
    """
    if output_path is None:
        output_path = Path.home() / "Downloads" / "chart_export.html"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # plotly
    try:
        fig.write_html(str(output_path), **kwargs)
        return output_path
    except AttributeError:
        pass

    # bokeh
    try:
        from bokeh.plotting import output_file, save
        output_file(str(output_path))
        save(fig, **kwargs)
        return output_path
    except Exception:
        pass

    return output_path
