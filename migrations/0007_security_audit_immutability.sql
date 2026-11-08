-- Make authentication/session audit records immutable.
BEGIN;

CREATE TRIGGER security_audit_events_append_only
BEFORE UPDATE OR DELETE ON security_audit_events
FOR EACH ROW EXECUTE FUNCTION reject_immutable_record_mutation();

COMMIT;
