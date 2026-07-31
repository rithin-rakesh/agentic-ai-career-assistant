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
from app.resume.template_preservation import ResumeTemplatePreservation
from app.logger import logger

class ResumeDocumentGenerator:
    """
    Generates customized resume documents in Markdown, DOCX, and PDF formats,
    preserving the canonical master resume template styling and layout parameters.
    """
    def __init__(self, master_template_path: str = None):
        self.config = DocumentTemplateConfig
        self.master_template_path = master_template_path or settings.RESUME_TEMPLATE
        self.template_metadata = ResumeTemplatePreservation.extract_template_metadata(self.master_template_path)

    def generate(self, resume_markdown: str, output_base_path: str) -> Dict[str, str]:
        """
        Saves tailored resume markdown, and compiles it into Word (.docx) and PDF (.pdf) formats.
        Returns: Dict mapping file types to absolute paths.
        """
        # Ensure directories exist
        os.makedirs(os.path.dirname(output_base_path), exist_ok=True)
        
        generated_paths = {}

        # 1. Save Markdown
        md_path = f"{output_base_path}.md"
        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(resume_markdown)
            generated_paths["markdown"] = md_path
            logger.info(f"ResumeGenerator: Saved Markdown resume to {md_path}")
        except Exception as e:
            logger.error(f"ResumeGenerator: Failed to save markdown: {e}")

        # 2. Compile DOCX
        if settings.DOCX_ENABLED:
            docx_path = f"{output_base_path}.docx"
            try:
                self._compile_docx(resume_markdown, docx_path)
                generated_paths["docx"] = docx_path
                logger.info(f"ResumeGenerator: Saved DOCX resume to {docx_path}")
            except Exception as e:
                logger.error(f"ResumeGenerator: Failed to compile DOCX: {e}", exc_info=True)

        # 3. Compile PDF
        if settings.PDF_ENABLED:
            pdf_path = f"{output_base_path}.pdf"
            try:
                self._compile_pdf(resume_markdown, pdf_path)
                generated_paths["pdf"] = pdf_path
                logger.info(f"ResumeGenerator: Saved PDF resume to {pdf_path}")
            except Exception as e:
                logger.error(f"ResumeGenerator: Failed to compile PDF: {e}", exc_info=True)

        return generated_paths

    def _compile_docx(self, markdown_text: str, output_path: str) -> None:
        """
        Parses Markdown blocks and builds a styled Word DOCX document.
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
                continue

            # Heading 1 (e.g. # Name)
            if stripped.startswith("# "):
                h = doc.add_heading(stripped[2:], level=1)
                h.alignment = WD_ALIGN_PARAGRAPH.CENTER
                h.style.font.color.rgb = docx_color(self.config.PRIMARY_COLOR)
                h.style.font.size = Pt(20)
                h.style.font.name = self.config.PRIMARY_FONT
                
            # Heading 2 (e.g. ## Experience)
            elif stripped.startswith("## "):
                h = doc.add_heading(stripped[3:], level=2)
                h.style.font.color.rgb = docx_color(self.config.SECONDARY_COLOR)
                h.style.font.size = Pt(14)
                h.style.font.name = self.config.PRIMARY_FONT
                
            # Heading 3 (e.g. ### Lead AI Dev)
            elif stripped.startswith("### "):
                h = doc.add_heading(stripped[4:], level=3)
                h.style.font.size = Pt(12)
                h.style.font.name = self.config.PRIMARY_FONT
                
            # Bullet point (e.g. - Python/Flask backend)
            elif stripped.startswith("- ") or stripped.startswith("* "):
                bullet_text = stripped[2:]
                # Inline bold parser helper
                p = doc.add_paragraph(style="List Bullet")
                self._add_inline_runs(p, bullet_text)
                
            # Regular text
            else:
                p = doc.add_paragraph()
                self._add_inline_runs(p, stripped)

        doc.save(output_path)

    def _compile_pdf(self, markdown_text: str, output_path: str) -> None:
        """
        Parses Markdown blocks and compiles a PDF file via ReportLab platypus,
        referencing the canonical master resume template styling properties.
        """
        # Setup document template using extracted master margin
        margin = self.template_metadata.get("pdf_margin", self.config.PDF_MARGIN)
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=margin,
            leftMargin=margin,
            topMargin=margin,
            bottomMargin=margin
        )

        styles = getSampleStyleSheet()
        
        primary_color = self.template_metadata.get("primary_color", self.config.PRIMARY_COLOR)
        secondary_color = self.template_metadata.get("secondary_color", self.config.SECONDARY_COLOR)
        text_color = self.template_metadata.get("text_color", self.config.TEXT_COLOR)
        font_primary = self.template_metadata.get("font_primary", self.config.PRIMARY_FONT)
        font_bold = self.template_metadata.get("font_bold", self.config.BOLD_FONT)
        
        # Define paragraph styles with master template visual properties
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Normal"],
            fontName=font_bold,
            fontSize=self.template_metadata.get("font_size_title", 18),
            leading=22,
            textColor=HexColor(primary_color),
            alignment=1 if self.template_metadata.get("alignment_header") == "center" else 0,
            spaceAfter=12
        )
        
        h1_style = ParagraphStyle(
            "DocH1",
            parent=styles["Normal"],
            fontName=font_bold,
            fontSize=self.template_metadata.get("font_size_h1", 13),
            leading=16,
            textColor=HexColor(secondary_color),
            spaceBefore=10,
            spaceAfter=4,
            keepWithNext=True
        )

        h2_style = ParagraphStyle(
            "DocH2",
            parent=styles["Normal"],
            fontName=font_bold,
            fontSize=self.template_metadata.get("font_size_h2", 11),
            leading=14,
            textColor=HexColor(text_color),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True
        )

        body_style = ParagraphStyle(
            "DocBody",
            parent=styles["Normal"],
            fontName=font_primary,
            fontSize=self.template_metadata.get("font_size_body", 9.5),
            leading=13,
            textColor=HexColor(text_color),
            spaceAfter=3
        )

        bullet_style = ParagraphStyle(
            "DocBullet",
            parent=styles["Normal"],
            fontName=font_primary,
            fontSize=self.template_metadata.get("font_size_body", 9.5),
            leading=13,
            textColor=HexColor(text_color),
            leftIndent=15,
            firstLineIndent=-10,
            spaceAfter=2
        )

        story = []
        lines = markdown_text.splitlines()

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Heading 1
            if stripped.startswith("# "):
                story.append(Paragraph(stripped[2:], title_style))
                story.append(Spacer(1, 4))
            # Heading 2
            elif stripped.startswith("## "):
                story.append(Paragraph(stripped[3:], h1_style))
            # Heading 3
            elif stripped.startswith("### "):
                story.append(Paragraph(stripped[4:], h2_style))
            # Bullet list
            elif stripped.startswith("- ") or stripped.startswith("* "):
                # Convert markdown bold to html tags for ReportLab Paragraph rendering
                bullet_html = self._md_to_html_bold(stripped[2:])
                story.append(Paragraph(f"&bull; {bullet_html}", bullet_style))
            # Normal text
            else:
                body_html = self._md_to_html_bold(stripped)
                story.append(Paragraph(body_html, body_style))

        doc.build(story)

    def _md_to_html_bold(self, text: str) -> str:
        """
        Converts markdown bold syntax `**text**` to HTML `<b>text</b>` for ReportLab compatibility.
        """
        import re
        return re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

    def _add_inline_runs(self, paragraph, md_line: str) -> None:
        """
        Parses bold `**` markers and populates Word runs inline.
        """
        import re
        tokens = re.split(r"(\*\*.*?\*\*)", md_line)
        for token in tokens:
            if token.startswith("**") and token.endswith("**"):
                run = paragraph.add_run(token[2:-2])
                run.bold = True
            else:
                paragraph.add_run(token)

def docx_color(hex_str: str):
    """
    Helper converting Hex string to docx RGBColor instance.
    """
    from docx.shared import RGBColor
    h = hex_str.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return RGBColor(r, g, b)
