"""Allow multiple teachers per course."""

from alembic import op
import sqlalchemy as sa

revision = "36d2ca681607"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    constraints = inspector.get_unique_constraints("users")

    if any(
        constraint["name"] == "users_course_id_key"
        for constraint in constraints
    ):
        op.drop_constraint(
            "users_course_id_key",
            "users",
            type_="unique",
        )


def downgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    constraints = inspector.get_unique_constraints("users")

    if not any(
        constraint["name"] == "users_course_id_key"
        for constraint in constraints
    ):
        op.create_unique_constraint(
            "users_course_id_key",
            "users",
            ["course_id"],
        )
