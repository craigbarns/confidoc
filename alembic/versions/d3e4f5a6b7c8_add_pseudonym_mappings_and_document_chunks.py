"""Add pseudonym mappings and optional document chunks

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-04-23 00:00:00.000000

"""

from alembic import op

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pseudonym_mappings (
            id uuid PRIMARY KEY,
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            updated_at timestamp with time zone NOT NULL DEFAULT now(),
            document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            encrypted_mapping text NOT NULL,
            expires_at timestamp with time zone,
            human_validated boolean NOT NULL DEFAULT false,
            validated_by_user_id uuid,
            validated_at timestamp with time zone,
            risk_score double precision,
            risk_level varchar(20)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pseudonym_mappings_document_id
            ON pseudonym_mappings (document_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pseudonym_mappings_user_id
            ON pseudonym_mappings (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_pseudonym_mappings_expires_at
            ON pseudonym_mappings (expires_at)
        """
    )

    # PGvector is optional in ConfiDoc deployments. Create the RAG table only
    # when the database supports the extension; the app degrades gracefully.
    op.execute(
        """
        DO $$
        BEGIN
            BEGIN
                CREATE EXTENSION IF NOT EXISTS vector;
            EXCEPTION WHEN undefined_file OR insufficient_privilege THEN
                RAISE NOTICE 'pgvector unavailable; skipping document_chunks';
            END;

            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id uuid PRIMARY KEY,
                    created_at timestamp with time zone NOT NULL DEFAULT now(),
                    updated_at timestamp with time zone NOT NULL DEFAULT now(),
                    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_text text NOT NULL,
                    chunk_index integer NOT NULL,
                    embedding vector(1024) NOT NULL,
                    source_section varchar(100)
                );

                CREATE INDEX IF NOT EXISTS ix_document_chunks_document_id
                    ON document_chunks (document_id);
                CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding
                    ON document_chunks
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding;")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_document_id;")
    op.execute("DROP TABLE IF EXISTS document_chunks;")
    op.execute("DROP INDEX IF EXISTS ix_pseudonym_mappings_expires_at;")
    op.execute("DROP INDEX IF EXISTS ix_pseudonym_mappings_user_id;")
    op.execute("DROP INDEX IF EXISTS ix_pseudonym_mappings_document_id;")
    op.execute("DROP TABLE IF EXISTS pseudonym_mappings;")
