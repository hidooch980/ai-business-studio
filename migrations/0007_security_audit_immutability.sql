-- Make authentication/session audit records immutable.
BEGIN;

CREATE TRIGGER security_audit_events_append_only
BEFORE UPDATE OR DELETE ON security_audit_events
FOR EACH ROW EXECUTE FUNCTION reject_immutable_record_mutation();

DROP POLICY tenant_isolation ON security_audit_events;

CREATE POLICY security_audit_insert_own_actor
ON security_audit_events
FOR INSERT
WITH CHECK (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    AND actor_identity_id = nullif(current_setting('app.subject_id', true), '')::uuid
);

CREATE POLICY security_audit_read_owner_admin
ON security_audit_events
FOR SELECT
USING (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    AND EXISTS (
        SELECT 1
        FROM tenant_memberships tm
        WHERE tm.tenant_id = security_audit_events.tenant_id
          AND tm.identity_id = nullif(current_setting('app.subject_id', true), '')::uuid
          AND tm.status = 'active'
          AND tm.role = 'owner_admin'
    )
);

COMMIT;
