"""Add teacher subject assignments."""

from alembic import op
import sqlalchemy as sa

revision = "dfea8bfe9e07"
down_revision = "36d2ca681607"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if not inspector.has_table("teacher_subjects"):
        op.create_table(
            "teacher_subjects",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("teacher_id", sa.Integer(), nullable=False),
            sa.Column("subject_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(
                ["subject_id"], ["subjects.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["teacher_id"], ["users.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("teacher_id", "subject_id"),
        )

    inspector = sa.inspect(connection)
    existing_indexes = {
        index["name"] for index in inspector.get_indexes("teacher_subjects")
    }

    if op.f("ix_teacher_subjects_subject_id") not in existing_indexes:
        op.create_index(
            op.f("ix_teacher_subjects_subject_id"),
            "teacher_subjects",
            ["subject_id"],
            unique=False,
        )

    if op.f("ix_teacher_subjects_teacher_id") not in existing_indexes:
        op.create_index(
            op.f("ix_teacher_subjects_teacher_id"),
            "teacher_subjects",
            ["teacher_id"],
            unique=False,
        )


def downgrade():
    op.drop_index(
        op.f("ix_teacher_subjects_teacher_id"),
        table_name="teacher_subjects",
    )
    op.drop_index(
        op.f("ix_teacher_subjects_subject_id"),
        table_name="teacher_subjects",
    )
    op.drop_table("teacher_subjects")
