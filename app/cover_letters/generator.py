import os
from typing import Dict, Any
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor

from app.config import settings
from app.resume.template_engine import DocumentTemplateConfig
from app.logger import logger

class CoverLetterGenerator:
    """
    Generates personalized cover letter documents in Markdown, DOCX, and PDF formats.
    """
    def __init__(self):
        self.config = DocumentTemplateConfig

    def generate(self, cl_text_markdown: str, output_base_path: str) -> Dict[str, str]:
        """
        Saves cover letter markdown, and compiles it into Word (.docx) and PDF (.pdf) formats.
        Returns: Dict mapping file types to absolute paths.
        """
        os.makedirs(os.path.dirname(output_base_path), exist_ok=True)
        
        generated_paths = {}

        # 1. Save Markdown
        md_path = f"{output_base_path}.md"
        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(cl_text_markdown)
            generated_paths["markdown"] = md_path
            logger.info(f"CoverLetterGenerator: Saved Markdown Cover Letter to {md_path}")
        except Exception as e:
            logger.error(f"CoverLetterGenerator: Failed to save markdown: {e}")

        # 2. Compile DOCX
        if settings.DOCX_ENABLED:
            docx_path = f"{output_base_path}.docx"
            try:
                self._compile_docx(cl_text_markdown, docx_path)
                generated_paths["docx"] = docx_path
                logger.info(f"CoverLetterGenerator: Saved DOCX Cover Letter to {docx_path}")
            except Exception as e:
                logger.error(f"CoverLetterGenerator: Failed to compile DOCX: {e}", exc_info=True)

        # 3. Compile PDF
        if settings.PDF_ENABLED:
            pdf_path = f"{output_base_path}.pdf"
            try:
                self._compile_pdf(cl_text_markdown, pdf_path)
                generated_paths["pdf"] = pdf_path
                logger.info(f"CoverLetterGenerator: Saved PDF Cover Letter to {pdf_path}")
            except Exception as e:
                logger.error(f"CoverLetterGenerator: Failed to compile PDF: {e}", exc_info=True)

        return generated_paths

    def _compile_docx(self, markdown_text: str, output_path: str) -> None:
        """
        Parses Markdown blocks and builds a styled Cover Letter in DOCX.
        """
        doc = Document()
        
        # Set margins
        for section in doc.sections:
            section.top_margin = Inches(self.config.DOCX_MARGIN)
            section.bottom_margin = Inches(self.config.DOCX_MARGIN)
            section.left_margin = Inches(self.config.DOCX_MARGIN)
            section.right_margin = Inches(self.config.DOCX_MARGIN)

        lines = markdown_text.splitlines()
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                # Add spacer paragraph
                doc.add_paragraph()
                continue

            # Heading 1 (Letter head title or candidate name)
            if stripped.startswith("# "):
                h = doc.add_heading(stripped[2:], level=1)
                h.alignment = WD_ALIGN_PARAGRAPH.LEFT
                h.style.font.color.rgb = docx_color(self.config.PRIMARY_COLOR)
                h.style.font.size = Pt(18)
                h.style.font.name = self.config.PRIMARY_FONT
                
            # Heading 2 (e.g. date or company address)
            elif stripped.startswith("## "):
                h = doc.add_heading(stripped[3:], level=2)
                h.style.font.color.rgb = docx_color(self.config.SECONDARY_COLOR)
                h.style.font.size = Pt(12)
                h.style.font.name = self.config.PRIMARY_FONT
                
            # Body Paragraph
            else:
                p = doc.add_paragraph()
                p.style.font.size = Pt(11)
                p.style.font.name = self.config.PRIMARY_FONT
                self._add_inline_runs(p, stripped)

        doc.save(output_path)

    def _compile_pdf(self, markdown_text: str, output_path: str) -> None:
        """
        Parses Markdown blocks and compiles a PDF Cover Letter via ReportLab.
        """
        margin = self.config.PDF_MARGIN
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=margin,
            leftMargin=margin,
            topMargin=margin,
            bottomMargin=margin
        )

        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            "CLTitle",
            parent=styles["Normal"],
            fontName=self.config.BOLD_FONT,
            fontSize=16,
            leading=20,
            textColor=HexColor(self.config.PRIMARY_COLOR),
            spaceAfter=12
        )
        
        meta_style = ParagraphStyle(
            "CLMeta",
            parent=styles["Normal"],
            fontName=self.config.PRIMARY_FONT,
            fontSize=10,
            leading=14,
            textColor=HexColor(self.config.SECONDARY_COLOR),
            spaceAfter=10
        )

        body_style = ParagraphStyle(
            "CLBody",
            parent=styles["Normal"],
            fontName=self.config.PRIMARY_FONT,
            fontSize=10,
            leading=15,
            textColor=HexColor(self.config.TEXT_COLOR),
            spaceAfter=12
        )

        story = []
        lines = markdown_text.splitlines()

        for line in lines:
            stripped = line.strip()
            if not stripped:
                story.append(Spacer(1, 8))
                continue

            # Heading 1
            if stripped.startswith("# "):
                story.append(Paragraph(stripped[2:], title_style))
            # Heading 2
            elif stripped.startswith("## "):
                story.append(Paragraph(stripped[3:], meta_style))
            # Normal text body
            else:
                body_html = self._md_to_html_bold(stripped)
                story.append(Paragraph(body_html, body_style))

        doc.build(story)

    def _md_to_html_bold(self, text: str) -> str:
        import re
        return re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

    def _add_inline_runs(self, paragraph, md_line: str) -> None:
        import re
        tokens = re.split(r"(\*\*.*?\*\*)", md_line)
        for token in tokens:
            if token.startswith("**") and token.endswith("**"):
                run = paragraph.add_run(token[2:-2])
                run.bold = True
            else:
                paragraph.add_run(token)

def docx_color(hex_str: str):
    from docx.shared import RGBColor
    h = hex_str.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return RGBColor(r, g, b)
