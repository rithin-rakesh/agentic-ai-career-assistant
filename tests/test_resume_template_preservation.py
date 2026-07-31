import os
import pytest
from datetime import datetime, timezone
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, ResumeVersionModel
from app.database.repository import JobRepository
from app.resume.template_preservation import ResumeTemplatePreservation
from app.resume.resume_generator import ResumeDocumentGenerator

@pytest.fixture
def mock_db_provider():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    @contextmanager
    def _provider():
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            
    return _provider


def test_extract_template_metadata_defaults():
    """
    Verifies default template styling parameters returned when no template exists.
    """
    meta = ResumeTemplatePreservation.extract_template_metadata("non_existent_file.pdf")
    assert "primary_color" in meta
    assert "pdf_margin" in meta
    assert meta["pdf_margin"] == 54
    assert meta["docx_margin"] == 0.75
    assert meta["font_primary"] == "Helvetica"


def test_extract_template_metadata_from_text_file(tmp_path):
    """
    Verifies layout metrics and section header extraction from text/markdown master resume.
    """
    master_file = tmp_path / "master_resume.md"
    master_file.write_text(
        "# ALEX MERCER\n"
        "alex@example.com | +1 (555) 019-2834 | San Francisco, CA\n\n"
        "## PROFESSIONAL EXPERIENCE\n"
        "- Senior AI Engineer at Quantum Corp\n\n"
        "## EDUCATION\n"
        "BS Computer Science, Stanford\n"
    )

    meta = ResumeTemplatePreservation.extract_template_metadata(str(master_file))
    assert "ALEX MERCER" in meta["contact_header"]
    assert len(meta["section_titles"]) >= 2


def test_assemble_tailored_resume_markdown():
    """
    Verifies that tailoring strictly preserves original contact header while updating
    only allowed editable content sections (Professional Summary, Skills).
    """
    master_text = (
        "# JANE DOE\n"
        "jane@example.com | Seattle, WA\n\n"
        "## EXPERIENCE\n"
        "- Lead Engineer\n"
    )

    tailored_summary = "Pioneer in distributed LangGraph agents and high-throughput vector systems."
    tailored_skills = ["Python", "FastAPI", "Qdrant", "PyTorch"]

    result = ResumeTemplatePreservation.assemble_tailored_resume_markdown(
        master_raw_text=master_text,
        tailored_summary=tailored_summary,
        tailored_skills=tailored_skills
    )

    # Contact header must be preserved
    assert "# JANE DOE" in result
    assert "jane@example.com | Seattle, WA" in result
    # Tailored sections must be present
    assert "Professional Summary" in result
    assert "distributed LangGraph" in result
    assert "FastAPI, Qdrant" in result


def test_resume_document_generator_uses_master_template(tmp_path):
    """
    Verifies ResumeDocumentGenerator initializes template metadata and compiles PDF & MD outputs.
    """
    master_file = tmp_path / "master.md"
    master_file.write_text("# John Doe\nDeveloper")

    generator = ResumeDocumentGenerator(master_template_path=str(master_file))
    assert generator.template_metadata["font_primary"] == "Helvetica"

    output_base = str(tmp_path / "tailored_john_doe")
    paths = generator.generate("# John Doe\nTailored AI Engineer", output_base)

    assert "markdown" in paths
    assert os.path.exists(paths["markdown"])
    assert "pdf" in paths
    assert os.path.exists(paths["pdf"])


def test_master_template_file_storage_and_versioning(mock_db_provider):
    """
    Verifies ResumeVersionModel tracks uploaded master template versions and active state.
    """
    repo = JobRepository(session_provider=mock_db_provider)
    now_utc = datetime.now(timezone.utc)

    with repo.session_provider() as session:
        v1 = ResumeVersionModel(
            filename="master_v1.pdf",
            file_path="data/resumes/master_v1.pdf",
            file_hash="hash_abc_123",
            version=1,
            is_active=True,
            upload_date=now_utc,
            embedding_status="Indexed",
            chunk_count=4
        )
        session.add(v1)
        session.flush()

        active = repo.get_active_resume_version()
        assert active is not None
        assert active.version == 1
        assert active.file_hash == "hash_abc_123"
