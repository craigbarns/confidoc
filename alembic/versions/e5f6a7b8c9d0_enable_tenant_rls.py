"""Enable tenant Row Level Security

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-07 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def _tenant_expr(
    column: str = "org_id",
    *,
    nullable: bool = False,
    owner_column: str | None = None,
) -> str:
    scoped = f"{column} = public.confidoc_rls_current_org_id()"
    if nullable:
        legacy_scoped = f"{column} IS NULL"
        if owner_column:
            legacy_scoped = (
                f"({legacy_scoped} AND {owner_column} = public.confidoc_rls_current_user_id())"
            )
        scoped = f"({scoped} OR {legacy_scoped})"
    return f"(public.confidoc_rls_bypass() OR {scoped})"


def _document_child_expr(table: str, column: str = "document_id") -> str:
    return f"""
    (
        public.confidoc_rls_bypass()
        OR EXISTS (
            SELECT 1
            FROM public.documents d
            WHERE d.id = {table}.{column}
              AND (
                d.org_id = public.confidoc_rls_current_org_id()
                OR (
                    d.org_id IS NULL
                    AND d.uploaded_by_user_id = public.confidoc_rls_current_user_id()
                )
              )
        )
    )
    """


def _golden_draft_expr() -> str:
    return """
    (
        public.confidoc_rls_bypass()
        OR (
            org_id = public.confidoc_rls_current_org_id()
            AND EXISTS (
                SELECT 1
                FROM public.documents d
                WHERE d.id = golden_case_drafts.document_id
                  AND d.org_id = public.confidoc_rls_current_org_id()
            )
        )
    )
    """


def _apply_policy(table: str, using_expr: str, check_expr: str | None = None) -> None:
    policy = f"rls_{table}_tenant_isolation"
    check = check_expr or using_expr
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('public.{table}') IS NOT NULL THEN
                EXECUTE 'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY';
                EXECUTE 'ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY';
                EXECUTE 'DROP POLICY IF EXISTS {policy} ON public.{table}';
                EXECUTE $policy$
                    CREATE POLICY {policy}
                    ON public.{table}
                    FOR ALL
                    USING ({using_expr})
                    WITH CHECK ({check})
                $policy$;
            END IF;
        END $$;
        """
    )


def _drop_policy(table: str) -> None:
    policy = f"rls_{table}_tenant_isolation"
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('public.{table}') IS NOT NULL THEN
                EXECUTE 'DROP POLICY IF EXISTS {policy} ON public.{table}';
                EXECUTE 'ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY';
                EXECUTE 'ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY';
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.confidoc_rls_current_org_id()
        RETURNS uuid
        LANGUAGE plpgsql
        STABLE
        AS $$
        DECLARE
            raw_org_id text;
        BEGIN
            raw_org_id := current_setting('app.current_org_id', true);
            IF raw_org_id IS NULL OR raw_org_id = '' THEN
                RETURN NULL;
            END IF;
            RETURN raw_org_id::uuid;
        EXCEPTION WHEN invalid_text_representation THEN
            RETURN NULL;
        END;
        $$;

        CREATE OR REPLACE FUNCTION public.confidoc_rls_current_user_id()
        RETURNS uuid
        LANGUAGE plpgsql
        STABLE
        AS $$
        DECLARE
            raw_user_id text;
        BEGIN
            raw_user_id := current_setting('app.current_user_id', true);
            IF raw_user_id IS NULL OR raw_user_id = '' THEN
                RETURN NULL;
            END IF;
            RETURN raw_user_id::uuid;
        EXCEPTION WHEN invalid_text_representation THEN
            RETURN NULL;
        END;
        $$;

        CREATE OR REPLACE FUNCTION public.confidoc_rls_bypass()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        AS $$
            SELECT COALESCE(current_setting('app.rls_bypass', true), 'off') = 'on';
        $$;
        """
    )

    _apply_policy("documents", _tenant_expr(nullable=True, owner_column="uploaded_by_user_id"))
    _apply_policy("clients", _tenant_expr())
    _apply_policy("dossiers", _tenant_expr())
    _apply_policy("api_keys", _tenant_expr())
    _apply_policy("webhook_endpoints", _tenant_expr())
    _apply_policy("webhook_deliveries", _tenant_expr())
    _apply_policy(
        "idempotency_records",
        _tenant_expr(nullable=True, owner_column="created_by_user_id"),
    )
    _apply_policy("audit_logs", _tenant_expr(nullable=True))

    golden_expr = _golden_draft_expr()
    _apply_policy("golden_case_drafts", golden_expr)

    for table in (
        "document_versions",
        "entity_detections",
        "pseudonym_mappings",
        "document_chunks",
        "llm_requests",
    ):
        _apply_policy(table, _document_child_expr(table))


def downgrade() -> None:
    for table in (
        "llm_requests",
        "document_chunks",
        "pseudonym_mappings",
        "entity_detections",
        "document_versions",
        "golden_case_drafts",
        "audit_logs",
        "idempotency_records",
        "webhook_deliveries",
        "webhook_endpoints",
        "api_keys",
        "dossiers",
        "clients",
        "documents",
    ):
        _drop_policy(table)

    op.execute(
        """
        DROP FUNCTION IF EXISTS public.confidoc_rls_bypass();
        DROP FUNCTION IF EXISTS public.confidoc_rls_current_user_id();
        DROP FUNCTION IF EXISTS public.confidoc_rls_current_org_id();
        """
    )
