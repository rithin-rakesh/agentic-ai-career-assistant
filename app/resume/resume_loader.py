import os
from typing import Optional
from app.logger import logger

class ResumeLoader:
    """
    Utility class for loading resumes from disk.
    Supports reading from plain text, Markdown (.md), and PDF (.pdf) formats.
    """
    @staticmethod
    def load_resume(file_path: str) -> str:
        """
        Reads resume content from the specified filepath.
        Selects parser dynamically based on file extension.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Resume file not found at path: {file_path}")
            
        _, ext = os.path.splitext(file_path.lower())
        
        logger.info(f"Loading resume from: {file_path} (Format: {ext})")
        
        if ext in (".md", ".txt"):
            return ResumeLoader._load_text(file_path)
        elif ext == ".pdf":
            return ResumeLoader._load_pdf(file_path)
        else:
            raise ValueError(f"Unsupported resume file format: {ext}. Must be .md, .txt, or .pdf")

    @staticmethod
    def _load_text(file_path: str) -> str:
        """
        Loads plain text or Markdown files.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            if not content.strip():
                raise ValueError("Resume file is empty.")
            return content
        except Exception as e:
            logger.error(f"Failed to read text/markdown resume: {e}", exc_info=True)
            raise

    @staticmethod
    def _load_pdf(file_path: str) -> str:
        """
        Loads PDF files using pypdf.
        """
        try:
            # Import pypdf inside function to ensure package is installed first
            import pypdf
            
            reader = pypdf.PdfReader(file_path)
            text_parts = []
            
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    text_parts.append(text)
                    
            full_text = "\n".join(text_parts)
            if not full_text.strip():
                raise ValueError("Could not extract any text content from PDF. It might be scanned or empty.")
                
            return full_text
        except ImportError:
            logger.error("pypdf package is not installed. Unable to parse PDF files.", exc_info=True)
            raise RuntimeError("pypdf package missing. Install via pip install pypdf.")
        except Exception as e:
            err_str = str(e).lower()
            if "pdf" in err_str or "stream" in err_str or "header" in err_str or "EOF" in str(e) or "xref" in err_str:
                logger.error(f"Corrupted or invalid PDF resume file '{file_path}': {e}", exc_info=True)
                raise ValueError(f"Corrupted or unreadable PDF file: {e}")
            logger.error(f"Failed to parse PDF resume: {e}", exc_info=True)
            raise
