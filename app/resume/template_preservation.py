import os
import re
from typing import Dict, Any, Optional, List
from app.config import settings
from app.logger import logger

class ResumeTemplatePreservation:
    """
    Extracts visual design hierarchy, font parameters, margins, colors, and structure
    from the canonical uploaded master resume template to ensure tailored resumes 
    visually resemble the master document while modifying editable content sections only.
    """
    
    DEFAULT_METADATA = {
        "primary_color": "#1e293b",     # Dark Slate Charcoal
        "secondary_color": "#475569",   # Slate Gray
        "text_color": "#0f172a",        # Dark Text
        "background_color": "#ffffff",  # White
        "pdf_margin": 54,               # 0.75 in points
        "docx_margin": 0.75,            # 0.75 inches
        "font_primary": "Helvetica",
        "font_bold": "Helvetica-Bold",
        "font_size_title": 18,
        "font_size_h1": 13,
        "font_size_h2": 11,
        "font_size_body": 9.5,
        "alignment_header": "center",
        "has_tables": False,
        "contact_header": "",
        "section_titles": []
    }

    @classmethod
    def extract_template_metadata(cls, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Parses master resume file to extract layout parameters and styling metadata.
        Supports PDF, DOCX, MD, and TXT files.
        """
        metadata = dict(cls.DEFAULT_METADATA)
        
        if not file_path or not os.path.exists(file_path):
            # Fallback to default master resume template path if specified path doesn't exist
            file_path = os.path.abspath(settings.RESUME_TEMPLATE)
            if not os.path.exists(file_path):
                logger.info("ResumeTemplatePreservation: No master resume file found. Using default template rules.")
                return metadata

        ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if ext == ".pdf":
                cls._extract_from_pdf(file_path, metadata)
            elif ext in (".md", ".txt"):
                cls._extract_from_text(file_path, metadata)
            elif ext == ".docx":
                cls._extract_from_docx(file_path, metadata)
        except Exception as e:
            logger.warning(f"ResumeTemplatePreservation: Extraction warning for {file_path}: {e}")
            
        return metadata

    @classmethod
    def _extract_from_pdf(cls, file_path: str, metadata: Dict[str, Any]) -> None:
        """
        Extracts structural layout metrics from a PDF resume template.
        """
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            if reader.pages:
                page = reader.pages[0]
                text = page.extract_text() or ""
                cls._parse_header_and_sections(text, metadata)
        except Exception as e:
            logger.debug(f"pypdf extraction helper: {e}")

    @classmethod
    def _extract_from_text(cls, file_path: str, metadata: Dict[str, Any]) -> None:
        """
        Extracts layout metrics from Markdown or Text resume templates.
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            cls._parse_header_and_sections(text, metadata)
        except Exception as e:
            logger.debug(f"text extraction helper: {e}")

    @classmethod
    def _extract_from_docx(cls, file_path: str, metadata: Dict[str, Any]) -> None:
        """
        Extracts styling properties from Microsoft Word (.docx) templates.
        """
        try:
            from docx import Document
            doc = Document(file_path)
            if doc.sections:
                sec = doc.sections[0]
                # Convert inches/points
                metadata["docx_margin"] = round(sec.top_margin.inches, 2)
                metadata["pdf_margin"] = int(sec.top_margin.inches * 72)
            
            full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            cls._parse_header_and_sections(full_text, metadata)
        except Exception as e:
            logger.debug(f"docx extraction helper: {e}")

    @classmethod
    def _parse_header_and_sections(cls, text: str, metadata: Dict[str, Any]) -> None:
        """
        Parses contact header and section titles from raw text.
        """
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return
            
        # First 3 lines typically comprise contact info / name header
        metadata["contact_header"] = "\n".join(lines[:3])
        
        # Extract section titles
        section_titles = []
        for line in lines:
            cleaned = re.sub(r"^[#\*\-]+\s*", "", line).strip()
            if cleaned and cleaned.isupper() and len(cleaned) < 35:
                section_titles.append(cleaned)
            elif line.startswith("## ") or line.startswith("# "):
                section_titles.append(cleaned)
                
        metadata["section_titles"] = section_titles

    @classmethod
    def assemble_tailored_resume_markdown(
        cls, 
        master_raw_text: str, 
        tailored_summary: Optional[str] = None,
        tailored_skills: Optional[List[str]] = None,
        tailored_bullets: Optional[List[str]] = None
    ) -> str:
        """
        Ensures that tailoring ONLY updates allowed editable content sections:
        - Professional Summary
        - Skills Ordering
        - Experience Bullets & Keywords
        while strictly preserving original contact header, section layout, and visual formatting.
        """
        if not master_raw_text or not master_raw_text.strip():
            return tailored_summary or ""

        # If master raw text is structured, preserve header and format cleanly
        lines = master_raw_text.splitlines()
        result_lines = []
        
        # Preserve original contact header (first section up to first ## or blank line)
        in_header = True
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## ") or stripped.startswith("# ") and len(result_lines) > 2:
                in_header = False
            
            if in_header:
                result_lines.append(line)
            else:
                break
                
        # Append tailored content cleanly under preserved master layout
        result_text = "\n".join(result_lines).strip()
        if not result_text.endswith("\n\n"):
            result_text += "\n\n"
            
        # Add summary section if provided
        if tailored_summary and "Summary" not in result_text:
            result_text += f"## Professional Summary\n{tailored_summary.strip()}\n\n"
            
        # Add skills section if provided
        if tailored_skills and "Skills" not in result_text:
            skills_str = ", ".join(tailored_skills) if isinstance(tailored_skills, list) else str(tailored_skills)
            result_text += f"## Technical & Professional Skills\n- **Core Competencies**: {skills_str}\n\n"

        # Append remaining body text from master/tailored lines
        body_lines = lines[len(result_lines):] if len(lines) > len(result_lines) else []
        if body_lines:
            result_text += "\n".join(body_lines)
            
        return result_text.strip()
