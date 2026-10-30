"""baseline schema

The complete GoldenGuide schema. Earlier pre-release migrations were folded into this one.

Revision ID: 0001
Revises:
Create Date: 2026-10-30 15:20:31.718093
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic to order migrations.
revision: str = '0001'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this change."""
    op.create_table('documents',
    sa.Column('document_id', sa.String(), nullable=False),
    sa.Column('source_type', sa.String(), nullable=False),
    sa.Column('source_ref', sa.String(), nullable=False),
    sa.Column('content_hash', sa.String(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('document_id')
    )
    op.create_index(op.f('ix_documents_content_hash'), 'documents', ['content_hash'], unique=False)
    op.create_table('job_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('job_name', sa.String(length=128), nullable=False),
    sa.Column('mode', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_job_runs_job_name'), 'job_runs', ['job_name'], unique=False)
    op.create_index(op.f('ix_job_runs_status'), 'job_runs', ['status'], unique=False)
    op.create_table('settings',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('key', sa.String(length=50), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_settings_key'), 'settings', ['key'], unique=False)
    op.create_table('job_batches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('batch_no', sa.Integer(), nullable=False),
    sa.Column('offset', sa.Integer(), nullable=False),
    sa.Column('batch_size', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('processed_count', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error_type', sa.String(length=256), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['job_runs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id', 'batch_no', name='uq_job_batches_run_batch_no')
    )
    op.create_index(op.f('ix_job_batches_run_id'), 'job_batches', ['run_id'], unique=False)
    op.create_index(op.f('ix_job_batches_status'), 'job_batches', ['status'], unique=False)
    op.create_table('courses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('academic_year', sa.String(length=16), nullable=False),
    sa.Column('institution', sa.String(length=64), nullable=False),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('subject_code', sa.String(length=32), nullable=False),
    sa.Column('course_number', sa.String(length=32), nullable=False),
    sa.Column('campus', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=512), nullable=True),
    sa.Column('calendar_url', sa.String(length=2048), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('prereq', sa.Text(), nullable=True),
    sa.Column('coreq', sa.Text(), nullable=True),
    sa.Column('exclusions', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('credit_min', sa.Float(), nullable=True),
    sa.Column('credit_max', sa.Float(), nullable=True),
    sa.Column('credit_unit', sa.String(length=32), nullable=True),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('needs_embedding', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('academic_year', 'institution', 'subject_code', 'course_number', name='uq_courses_identity')
    )
    op.create_index(op.f('ix_courses_academic_year'), 'courses', ['academic_year'], unique=False)
    op.create_index(op.f('ix_courses_campus'), 'courses', ['campus'], unique=False)
    op.create_index(op.f('ix_courses_course_number'), 'courses', ['course_number'], unique=False)
    op.create_index(op.f('ix_courses_credit_max'), 'courses', ['credit_max'], unique=False)
    op.create_index(op.f('ix_courses_credit_min'), 'courses', ['credit_min'], unique=False)
    op.create_index(op.f('ix_courses_institution'), 'courses', ['institution'], unique=False)
    op.create_index(op.f('ix_courses_needs_embedding'), 'courses', ['needs_embedding'], unique=False)
    op.create_index(op.f('ix_courses_subject_code'), 'courses', ['subject_code'], unique=False)
    op.create_table('scrape_pages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('version', sa.String(length=120), nullable=False),
    sa.Column('site_name', sa.String(length=120), nullable=False),
    sa.Column('parent_url', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('http_status', sa.Integer(), nullable=True),
    sa.Column('content_type', sa.String(length=120), nullable=True),
    sa.Column('blob_key', sa.Text(), nullable=True),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('retry_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_attempted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('etag', sa.String(length=128), nullable=True),
    sa.Column('last_modified_header', sa.String(length=128), nullable=True),
    sa.Column('needs_persistence', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('url', 'version', name='uq_scrape_pages_url_version')
    )
    op.create_index(op.f('ix_scrape_pages_needs_persistence'), 'scrape_pages', ['needs_persistence'], unique=False)
    op.create_index(op.f('ix_scrape_pages_parent_url'), 'scrape_pages', ['parent_url'], unique=False)
    op.create_index(op.f('ix_scrape_pages_site_name'), 'scrape_pages', ['site_name'], unique=False)
    op.create_index(op.f('ix_scrape_pages_status'), 'scrape_pages', ['status'], unique=False)
    op.create_index(op.f('ix_scrape_pages_version'), 'scrape_pages', ['version'], unique=False)
    op.create_table('wlu_pages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('url', sa.String(length=2048), nullable=False),
    sa.Column('version', sa.String(length=64), nullable=False),
    sa.Column('site_name', sa.String(length=64), nullable=False),
    sa.Column('record_type', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=512), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('needs_embedding', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version', 'url', name='uq_wlu_pages_identity')
    )
    op.create_index(op.f('ix_wlu_pages_needs_embedding'), 'wlu_pages', ['needs_embedding'], unique=False)
    op.create_index(op.f('ix_wlu_pages_record_type'), 'wlu_pages', ['record_type'], unique=False)
    op.create_index(op.f('ix_wlu_pages_site_name'), 'wlu_pages', ['site_name'], unique=False)
    op.create_index(op.f('ix_wlu_pages_version'), 'wlu_pages', ['version'], unique=False)
    op.create_table('course_terms',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course_id', sa.Integer(), nullable=False),
    sa.Column('term_code', sa.String(length=16), nullable=False),
    sa.Column('crn', sa.String(length=32), nullable=False),
    sa.Column('term_name', sa.String(length=64), nullable=True),
    sa.Column('title', sa.String(length=512), nullable=True),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('subject_code', sa.String(length=32), nullable=False),
    sa.Column('course_number', sa.String(length=32), nullable=False),
    sa.Column('section_code', sa.String(length=32), nullable=True),
    sa.Column('part_of_term', sa.String(length=32), nullable=True),
    sa.Column('schedule_type', sa.String(length=128), nullable=True),
    sa.Column('open_section', sa.Boolean(), nullable=True),
    sa.Column('instructional_method', sa.String(length=128), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('prereq', sa.Text(), nullable=True),
    sa.Column('coreq', sa.Text(), nullable=True),
    sa.Column('exclusions', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('restrictions', sa.Text(), nullable=True),
    sa.Column('credit_hours', sa.Float(), nullable=True),
    sa.Column('credit_hour_low', sa.Float(), nullable=True),
    sa.Column('credit_hour_high', sa.Float(), nullable=True),
    sa.Column('maximum_enrollment', sa.Integer(), nullable=True),
    sa.Column('enrollment', sa.Integer(), nullable=True),
    sa.Column('seats_available', sa.Integer(), nullable=True),
    sa.Column('wait_capacity', sa.Integer(), nullable=True),
    sa.Column('wait_count', sa.Integer(), nullable=True),
    sa.Column('wait_available', sa.Integer(), nullable=True),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('needs_embedding', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('term_code', 'crn', name='uq_course_terms_term_crn')
    )
    op.create_index(op.f('ix_course_terms_course_id'), 'course_terms', ['course_id'], unique=False)
    op.create_index(op.f('ix_course_terms_course_number'), 'course_terms', ['course_number'], unique=False)
    op.create_index(op.f('ix_course_terms_credit_hours'), 'course_terms', ['credit_hours'], unique=False)
    op.create_index(op.f('ix_course_terms_crn'), 'course_terms', ['crn'], unique=False)
    op.create_index(op.f('ix_course_terms_needs_embedding'), 'course_terms', ['needs_embedding'], unique=False)
    op.create_index(op.f('ix_course_terms_subject_code'), 'course_terms', ['subject_code'], unique=False)
    op.create_index(op.f('ix_course_terms_term_code'), 'course_terms', ['term_code'], unique=False)
    op.create_table('course_term_faculty',
    sa.Column('banner_id', sa.String(length=32), nullable=True),
    sa.Column('display_name', sa.String(length=255), nullable=True),
    sa.Column('email_address', sa.String(length=255), nullable=True),
    sa.Column('primary_indicator', sa.Boolean(), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course_term_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['course_term_id'], ['course_terms.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_course_term_faculty_banner_id'), 'course_term_faculty', ['banner_id'], unique=False)
    op.create_index(op.f('ix_course_term_faculty_course_term_id'), 'course_term_faculty', ['course_term_id'], unique=False)
    op.create_table('course_term_meetings',
    sa.Column('begin_time', sa.String(length=8), nullable=True),
    sa.Column('end_time', sa.String(length=8), nullable=True),
    sa.Column('building', sa.String(length=128), nullable=True),
    sa.Column('room', sa.String(length=128), nullable=True),
    sa.Column('monday', sa.Boolean(), nullable=True),
    sa.Column('tuesday', sa.Boolean(), nullable=True),
    sa.Column('wednesday', sa.Boolean(), nullable=True),
    sa.Column('thursday', sa.Boolean(), nullable=True),
    sa.Column('friday', sa.Boolean(), nullable=True),
    sa.Column('saturday', sa.Boolean(), nullable=True),
    sa.Column('sunday', sa.Boolean(), nullable=True),
    sa.Column('start_date', sa.String(length=32), nullable=True),
    sa.Column('end_date', sa.String(length=32), nullable=True),
    sa.Column('category', sa.String(length=32), nullable=True),
    sa.Column('schedule_type', sa.String(length=128), nullable=True),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course_term_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['course_term_id'], ['course_terms.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_course_term_meetings_building_room', 'course_term_meetings', ['building', 'room'], unique=False)
    op.create_index(op.f('ix_course_term_meetings_course_term_id'), 'course_term_meetings', ['course_term_id'], unique=False)


def downgrade() -> None:
    """Undo this change (used to roll back a deploy)."""
    op.drop_index(op.f('ix_course_term_meetings_course_term_id'), table_name='course_term_meetings')
    op.drop_index('ix_course_term_meetings_building_room', table_name='course_term_meetings')
    op.drop_table('course_term_meetings')
    op.drop_index(op.f('ix_course_term_faculty_course_term_id'), table_name='course_term_faculty')
    op.drop_index(op.f('ix_course_term_faculty_banner_id'), table_name='course_term_faculty')
    op.drop_table('course_term_faculty')
    op.drop_index(op.f('ix_course_terms_term_code'), table_name='course_terms')
    op.drop_index(op.f('ix_course_terms_subject_code'), table_name='course_terms')
    op.drop_index(op.f('ix_course_terms_needs_embedding'), table_name='course_terms')
    op.drop_index(op.f('ix_course_terms_crn'), table_name='course_terms')
    op.drop_index(op.f('ix_course_terms_credit_hours'), table_name='course_terms')
    op.drop_index(op.f('ix_course_terms_course_number'), table_name='course_terms')
    op.drop_index(op.f('ix_course_terms_course_id'), table_name='course_terms')
    op.drop_table('course_terms')
    op.drop_index(op.f('ix_wlu_pages_version'), table_name='wlu_pages')
    op.drop_index(op.f('ix_wlu_pages_site_name'), table_name='wlu_pages')
    op.drop_index(op.f('ix_wlu_pages_record_type'), table_name='wlu_pages')
    op.drop_index(op.f('ix_wlu_pages_needs_embedding'), table_name='wlu_pages')
    op.drop_table('wlu_pages')
    op.drop_index(op.f('ix_scrape_pages_version'), table_name='scrape_pages')
    op.drop_index(op.f('ix_scrape_pages_status'), table_name='scrape_pages')
    op.drop_index(op.f('ix_scrape_pages_site_name'), table_name='scrape_pages')
    op.drop_index(op.f('ix_scrape_pages_parent_url'), table_name='scrape_pages')
    op.drop_index(op.f('ix_scrape_pages_needs_persistence'), table_name='scrape_pages')
    op.drop_table('scrape_pages')
    op.drop_index(op.f('ix_courses_subject_code'), table_name='courses')
    op.drop_index(op.f('ix_courses_needs_embedding'), table_name='courses')
    op.drop_index(op.f('ix_courses_institution'), table_name='courses')
    op.drop_index(op.f('ix_courses_credit_min'), table_name='courses')
    op.drop_index(op.f('ix_courses_credit_max'), table_name='courses')
    op.drop_index(op.f('ix_courses_course_number'), table_name='courses')
    op.drop_index(op.f('ix_courses_campus'), table_name='courses')
    op.drop_index(op.f('ix_courses_academic_year'), table_name='courses')
    op.drop_table('courses')
    op.drop_index(op.f('ix_job_batches_status'), table_name='job_batches')
    op.drop_index(op.f('ix_job_batches_run_id'), table_name='job_batches')
    op.drop_table('job_batches')
    op.drop_index(op.f('ix_settings_key'), table_name='settings')
    op.drop_table('settings')
    op.drop_index(op.f('ix_job_runs_status'), table_name='job_runs')
    op.drop_index(op.f('ix_job_runs_job_name'), table_name='job_runs')
    op.drop_table('job_runs')
    op.drop_index(op.f('ix_documents_content_hash'), table_name='documents')
    op.drop_table('documents')
