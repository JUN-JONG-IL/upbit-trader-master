"""PDF report generator for portfolio reports."""
from __future__ import annotations


class PDFGenerator:
    def generate_pdf(self, report: str, output_path: str) -> None:
        raise NotImplementedError
