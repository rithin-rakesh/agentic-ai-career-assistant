"""Candidate profile and resume versions migration.

Revision ID: 002_profile_and_resume_versions
Revises: 001_initial_schema
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002_profile_and_resume_versions'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. candidate_profile
    op.create_table(
        'candidate_profile',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('linkedin', sa.String(), nullable=True),
        sa.Column('github', sa.String(), nullable=True),
        sa.Column('portfolio', sa.String(), nullable=True),
        sa.Column('years_of_experience', sa.Float(), nullable=True),
        sa.Column('preferred_salary', sa.String(), nullable=True),
        sa.Column('notice_period', sa.String(), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. resume_versions
    op.create_table(
        'resume_versions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('file_hash', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('upload_date', sa.DateTime(), nullable=False),
        sa.Column('extracted_text_path', sa.String(), nullable=True),
        sa.Column('embedding_status', sa.String(), nullable=False),
        sa.Column('last_indexed', sa.DateTime(), nullable=True),
        sa.Column('chunk_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_resume_versions_file_hash'), 'resume_versions', ['file_hash'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_resume_versions_file_hash'), table_name='resume_versions')
    op.drop_table('resume_versions')
    op.drop_table('candidate_profile')
