import os
from typing import Dict, Any

class DocumentTemplateConfig:
    """
    Shared visual styling parameters for Docx and PDF generation engines.
    """
    # Color palette
    PRIMARY_COLOR = "#4f46e5"      # Indigo
    SECONDARY_COLOR = "#475569"    # Slate Gray
    TEXT_COLOR = "#1e293b"         # Charcoal
    BACKGROUND_COLOR = "#f8fafc"   # Light Slate
    
    # Margin settings (in points for ReportLab, inches for python-docx)
    PDF_MARGIN = 54   # 0.75 inch (1 inch = 72 points)
    DOCX_MARGIN = 0.75 # 0.75 inch
    
    # Font options
    PRIMARY_FONT = "Helvetica"
    BOLD_FONT = "Helvetica-Bold"

    @classmethod
    def get_style_rules(cls) -> Dict[str, Any]:
        return {
            "primary": cls.PRIMARY_COLOR,
            "secondary": cls.SECONDARY_COLOR,
            "text": cls.TEXT_COLOR,
            "font": cls.PRIMARY_FONT,
            "font_bold": cls.BOLD_FONT
        }
