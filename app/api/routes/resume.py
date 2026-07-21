import os
import hashlib
import tempfile
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from app.auth.authentication import get_current_user
from app.config import settings
from app.logger import logger
from app.database.repository import JobRepository
from app.resume.resume_loader import ResumeLoader
from app.resume.chunk_generator import ResumeChunkGenerator
from app.rag.embedding_service import EmbeddingService
from app.rag.vector_store import VectorStore
from app.rag.indexing import ResumeIndexingPipeline

router = APIRouter(prefix="/api/resume", tags=["Resume"])

def _compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def process_and_index_resume(
    filename: str,
    raw_bytes: bytes,
    file_ext: str,
    repo: JobRepository
) -> Dict[str, Any]:
    """
    Executes the 9-step Resume Processing Workflow:
    Upload -> Validate -> Store -> Extract Text -> Chunk -> Generate Embeddings -> Update Qdrant -> Activate Resume -> Archive Previous Version.
    Uses file hashing to avoid unnecessary re-indexing.
    """
    # 1. Validate file extension and non-empty
    if not raw_bytes or len(raw_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded resume file is empty."
        )

    ext = file_ext.lower()
    if ext not in (".pdf", ".md", ".txt"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Please upload a PDF (.pdf) or Markdown (.md/.txt) document."
        )

    # 2. Extract Text & Validate Structure
    temp_dir = os.path.join(settings.BASE_DIR, "data", "temp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"upload_temp_{int(datetime.now().timestamp())}{ext}")

    try:
        with open(temp_path, "wb") as f:
            f.write(raw_bytes)

        extracted_text = ResumeLoader.load_resume(temp_path)
        if not extracted_text or not extracted_text.strip():
            raise ValueError("No extractable text content found in resume file.")
    except Exception as e:
        logger.error(f"Resume text extraction failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to extract text from resume: {e}"
        )
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

    # 3. Detect Changes using SHA-256 Hashing
    text_hash = _compute_hash(extracted_text)
    active_version = repo.get_active_resume_version()

    is_volatile_db = settings.VECTOR_DB_URL == ":memory:"
    if active_version and active_version.file_hash == text_hash and not is_volatile_db:
        logger.info(f"Resume file hash ({text_hash[:8]}) matches active version v{active_version.version}. Skipping re-indexing.")
        return {
            "status": "cached",
            "message": f"Resume unchanged. Version v{active_version.version} is already active and indexed.",
            "version": active_version.version,
            "filename": active_version.filename,
            "upload_date": active_version.upload_date.isoformat() if active_version.upload_date else None,
            "embedding_status": active_version.embedding_status,
            "last_indexed": active_version.last_indexed.isoformat() if active_version.last_indexed else None,
            "chunk_count": active_version.chunk_count,
            "is_active": True
        }

    # 4. Store PDF / Text files with versioning
    resumes_dir = os.path.join(settings.BASE_DIR, "data", "resumes")
    os.makedirs(resumes_dir, exist_ok=True)
    
    max_versions = repo.get_all_resume_versions()
    next_ver_num = (max_versions[0].version + 1) if max_versions else 1
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    saved_file_path = os.path.join(resumes_dir, f"resume_v{next_ver_num}_{timestamp_str}{ext}")
    saved_text_path = os.path.join(resumes_dir, f"resume_v{next_ver_num}_{timestamp_str}.md")

    with open(saved_file_path, "wb") as f:
        f.write(raw_bytes)

    with open(saved_text_path, "w", encoding="utf-8") as f:
        f.write(extracted_text)

    # Overwrite default data/resume.md for backward compatibility
    default_resume_path = os.path.abspath(settings.RESUME_TEMPLATE)
    os.makedirs(os.path.dirname(default_resume_path), exist_ok=True)
    with open(default_resume_path, "w", encoding="utf-8") as f:
        f.write(extracted_text)

    # Update resume hash cache file
    hash_file_path = os.path.join(settings.BASE_DIR, "data", "resume_hash.txt")
    with open(hash_file_path, "w", encoding="utf-8") as f:
        f.write(text_hash)

    # 5. Chunk, Generate Embeddings, Update Qdrant
    logger.info(f"Initiating chunking and embedding generation for resume v{next_ver_num}...")
    embedding_service = EmbeddingService()
    vector_store = VectorStore()

    chunks = ResumeChunkGenerator.generate_chunks(extracted_text)
    chunk_count = len(chunks)

    try:
        vector_store.rebuild_index()
        if chunks:
            contents = [chunk.content for chunk in chunks]
            embeddings = embedding_service.get_embeddings_batch(contents)
            for chunk, embedding in zip(chunks, embeddings):
                vector_store.insert_chunk(
                    chunk_id=chunk.chunk_id,
                    embedding=embedding,
                    metadata={"section": chunk.section},
                    content=chunk.content
                )
        embedding_status = "Indexed"
    except Exception as e:
        logger.error(f"Failed to update Qdrant vector DB: {e}", exc_info=True)
        embedding_status = "Failed"

    # 6. Activate Resume & Archive Previous Version
    new_version_record = repo.create_resume_version(
        filename=filename,
        file_path=saved_file_path,
        file_hash=text_hash,
        extracted_text_path=saved_text_path,
        chunk_count=chunk_count,
        embedding_status=embedding_status
    )

    logger.info(f"Resume: Activated version v{next_ver_num} ({filename}) with {chunk_count} chunks.")

    return {
        "status": "success",
        "message": f"Resume v{next_ver_num} uploaded, text extracted, and {chunk_count} chunks indexed successfully.",
        "version": new_version_record.version if new_version_record else next_ver_num,
        "filename": filename,
        "upload_date": new_version_record.upload_date.isoformat() if new_version_record else datetime.now(timezone.utc).isoformat(),
        "embedding_status": embedding_status,
        "last_indexed": new_version_record.last_indexed.isoformat() if new_version_record else datetime.now(timezone.utc).isoformat(),
        "chunk_count": chunk_count,
        "is_active": True
    }


@router.get("/status")
def get_resume_status(
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Retrieves metadata for the current active resume, embedding status, and version history.
    """
    active_version = repo.get_active_resume_version()
    all_versions = repo.get_all_resume_versions()

    # Read default data/resume.md fallback if DB has no record yet
    resume_text = ""
    default_path = os.path.abspath(settings.RESUME_TEMPLATE)
    if os.path.exists(default_path):
        try:
            with open(default_path, "r", encoding="utf-8") as f:
                resume_text = f.read()
        except Exception:
            pass

    if not active_version:
        # Generate virtual version metadata if default resume file exists
        hash_file = os.path.join(settings.BASE_DIR, "data", "resume_hash.txt")
        current_hash = ""
        if os.path.exists(hash_file):
            try:
                with open(hash_file, "r", encoding="utf-8") as f:
                    current_hash = f.read().strip()
            except Exception:
                pass
        if not current_hash and resume_text:
            current_hash = _compute_hash(resume_text)

        chunks = ResumeChunkGenerator.generate_chunks(resume_text) if resume_text else []

        active_meta = {
            "current_resume": os.path.basename(settings.RESUME_TEMPLATE),
            "filename": os.path.basename(settings.RESUME_TEMPLATE),
            "upload_date": datetime.now(timezone.utc).isoformat(),
            "version": 1,
            "embedding_status": "Indexed" if resume_text else "Pending",
            "last_indexed": datetime.now(timezone.utc).isoformat(),
            "chunk_count": len(chunks),
            "file_hash": current_hash,
            "is_active": True
        }
    else:
        active_meta = {
            "current_resume": active_version.filename,
            "filename": active_version.filename,
            "upload_date": active_version.upload_date.isoformat() if active_version.upload_date else None,
            "version": active_version.version,
            "embedding_status": active_version.embedding_status,
            "last_indexed": active_version.last_indexed.isoformat() if active_version.last_indexed else None,
            "chunk_count": active_version.chunk_count,
            "file_hash": active_version.file_hash,
            "is_active": True
        }

    archived = []
    for v in all_versions:
        if not v.is_active:
            archived.append({
                "version": v.version,
                "filename": v.filename,
                "upload_date": v.upload_date.isoformat() if v.upload_date else None,
                "chunk_count": v.chunk_count,
                "embedding_status": v.embedding_status
            })

    active_meta["archived_versions"] = archived
    return active_meta


@router.post("")
@router.post("/upload-pdf")
def upload_pdf_resume(
    file: Optional[UploadFile] = File(None, description="Resume PDF or Markdown file upload"),
    resume_text: Optional[str] = Form(None, description="Resume raw text"),
    repo: JobRepository = Depends(JobRepository),
    username: str = Depends(get_current_user)
):
    """
    Handles PDF or Markdown resume upload following the full automated workflow.
    Validates, extracts text, computes SHA-256 hash, stores versioned files, chunks, embeds into Qdrant, and archives previous versions.
    """
    if file:
        filename = file.filename or "uploaded_resume.pdf"
        _, ext = os.path.splitext(filename)
        if not ext:
            ext = ".pdf"
        raw_bytes = file.file.read()
        return process_and_index_resume(filename=filename, raw_bytes=raw_bytes, file_ext=ext, repo=repo)
    elif resume_text and resume_text.strip():
        filename = "resume.md"
        raw_bytes = resume_text.encode("utf-8")
        return process_and_index_resume(filename=filename, raw_bytes=raw_bytes, file_ext=".md", repo=repo)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file uploaded or resume text provided."
        )
