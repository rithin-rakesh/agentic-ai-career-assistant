"""Initial schema migration for PostgreSQL and SQLite.

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. jobs
    op.create_table(
        'jobs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('company', sa.String(), nullable=False),
        sa.Column('location', sa.String(), nullable=False),
        sa.Column('job_url', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('date_posted', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('match_score', sa.Integer(), nullable=True),
        sa.Column('should_apply', sa.Boolean(), nullable=True),
        sa.Column('priority', sa.String(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('strengths', sa.Text(), nullable=True),
        sa.Column('missing_skills', sa.Text(), nullable=True),
        sa.Column('learning_effort', sa.String(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('analysis_timestamp', sa.DateTime(), nullable=True),
        sa.Column('retrieved_chunk_ids', sa.Text(), nullable=True),
        sa.Column('retrieval_time', sa.Float(), nullable=True),
        sa.Column('embedding_model', sa.String(), nullable=True),
        sa.Column('retrieval_score', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_jobs_job_url'), 'jobs', ['job_url'], unique=True)

    # 2. applications
    op.create_table(
        'applications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('company', sa.String(), nullable=False),
        sa.Column('position', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('resume_path', sa.String(), nullable=True),
        sa.Column('cover_letter_path', sa.String(), nullable=True),
        sa.Column('applied_at', sa.DateTime(), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_applications_job_id'), 'applications', ['job_id'], unique=False)

    # 3. execution_logs
    op.create_table(
        'execution_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('node_name', sa.String(), nullable=False),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=False),
        sa.Column('duration', sa.Float(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('token_usage', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_execution_logs_node_name'), 'execution_logs', ['node_name'], unique=False)

    # 4. feedback_events
    op.create_table(
        'feedback_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=True),
        sa.Column('application_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('payload', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_feedback_events_event_type'), 'feedback_events', ['event_type'], unique=False)

    # 5. preferences
    op.create_table(
        'preferences',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('last_updated', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_preferences_category'), 'preferences', ['category'], unique=False)
    op.create_index(op.f('ix_preferences_name'), 'preferences', ['name'], unique=False)

    # 6. company_profiles
    op.create_table(
        'company_profiles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('applied_count', sa.Integer(), nullable=False),
        sa.Column('rejected_count', sa.Integer(), nullable=False),
        sa.Column('interview_count', sa.Integer(), nullable=False),
        sa.Column('offer_count', sa.Integer(), nullable=False),
        sa.Column('success_rate', sa.Float(), nullable=False),
        sa.Column('last_updated', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_company_profiles_name'), 'company_profiles', ['name'], unique=True)

    # 7. career_decisions
    op.create_table(
        'career_decisions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('recommendation', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('priority', sa.String(), nullable=False),
        sa.Column('estimated_interview_probability', sa.String(), nullable=False),
        sa.Column('career_growth', sa.String(), nullable=False),
        sa.Column('salary_competitiveness', sa.String(), nullable=False),
        sa.Column('learning_effort', sa.String(), nullable=False),
        sa.Column('resume_changes_required', sa.Boolean(), nullable=False),
        sa.Column('cover_letter_required', sa.Boolean(), nullable=False),
        sa.Column('estimated_application_time', sa.String(), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('missing_skills', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id')
    )

    # 8. learning_metrics
    op.create_table(
        'learning_metrics',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('metric_date', sa.DateTime(), nullable=False),
        sa.Column('accepted_recommendations', sa.Integer(), nullable=False),
        sa.Column('ignored_recommendations', sa.Integer(), nullable=False),
        sa.Column('interview_conversion_rate', sa.Float(), nullable=False),
        sa.Column('offer_conversion_rate', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 9. recommendation_history
    op.create_table(
        'recommendation_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('llm_match_score', sa.Float(), nullable=False),
        sa.Column('behavior_score', sa.Float(), nullable=False),
        sa.Column('company_preference_score', sa.Float(), nullable=False),
        sa.Column('location_preference_score', sa.Float(), nullable=False),
        sa.Column('technology_preference_score', sa.Float(), nullable=False),
        sa.Column('salary_match_score', sa.Float(), nullable=False),
        sa.Column('growth_score', sa.Float(), nullable=False),
        sa.Column('risk_score', sa.Float(), nullable=False),
        sa.Column('final_score', sa.Float(), nullable=False),
        sa.Column('recommendation_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_table('recommendation_history')
    op.drop_table('learning_metrics')
    op.drop_table('career_decisions')
    op.drop_table('company_profiles')
    op.drop_table('preferences')
    op.drop_table('feedback_events')
    op.drop_table('execution_logs')
    op.drop_table('applications')
    op.drop_table('jobs')
