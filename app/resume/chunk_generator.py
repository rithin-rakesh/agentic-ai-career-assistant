import re
from typing import List
from pydantic import BaseModel, Field
from app.logger import logger

class ResumeChunk(BaseModel):
    """
    Representation of a single logical chunk extracted from the candidate's resume.
    """
    chunk_id: str = Field(..., description="Unique slug for this chunk (e.g. section-skills)")
    section: str = Field(..., description="The resume section name (e.g. Skills, Experience)")
    content: str = Field(..., description="Raw text content of the chunk section")

class ResumeChunkGenerator:
    """
    Splits raw resume text into logical sections based on markdown headers.
    Attaches structured metadata to each section.
    """
    @staticmethod
    def generate_chunks(resume_text: str) -> List[ResumeChunk]:
        """
        Parses raw resume markdown text.
        Splits by headers (e.g. #, ##, ###) into logical section chunks.
        """
        if not resume_text or not resume_text.strip():
            logger.warning("Empty resume text provided. Generating zero chunks.")
            return []

        chunks: List[ResumeChunk] = []
        
        # Regular expression to match markdown headers (e.g., "# Header", "## Subheader")
        header_pattern = r"^(#{1,4})\s+(.+)$"
        lines = resume_text.splitlines()
        
        current_section = "General/Summary"
        current_content_lines = []
        chunk_counter = 1
        
        for line in lines:
            match = re.match(header_pattern, line.strip())
            if match:
                # If we have accumulated text for a previous section, save it first
                if current_content_lines:
                    content_body = "\n".join(current_content_lines).strip()
                    if content_body:
                        slug = current_section.lower().replace(" ", "-").replace("/", "-")
                        chunks.append(
                            ResumeChunk(
                                chunk_id=f"chunk-{chunk_counter}-{slug}",
                                section=current_section,
                                content=content_body
                            )
                        )
                        chunk_counter += 1
                
                # Setup next section
                current_section = match.group(2).strip()
                current_content_lines = [line]  # Keep the header as part of the chunk content for context!
            else:
                current_content_lines.append(line)
                
        # Save trailing section
        if current_content_lines:
            content_body = "\n".join(current_content_lines).strip()
            if content_body:
                slug = current_section.lower().replace(" ", "-").replace("/", "-")
                chunks.append(
                    ResumeChunk(
                        chunk_id=f"chunk-{chunk_counter}-{slug}",
                        section=current_section,
                        content=content_body
                    )
                )
                
        logger.info(f"Resume chunking complete. Split resume into {len(chunks)} logical sections.")
        return chunks
