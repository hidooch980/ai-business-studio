PERMISSION_CATALOG: tuple[tuple[str, str], ...] = (
    ("access.roles.read", "View tenant roles and permission catalog"),
    ("access.roles.manage", "Create tenant roles and configure permissions"),
    ("access.memberships.manage", "Assign roles to tenant memberships"),
    ("audit.read", "View tenant audit events"),
    ("users.read", "View tenant user directory"),
    ("users.manage", "Manage tenant memberships"),
    ("finance.read", "View financial records"),
    ("finance.write", "Create and update financial records"),
    ("inventory.read", "View inventory"),
    ("inventory.write", "Manage inventory"),
    ("sales.read", "View sales records"),
    ("sales.write", "Create and update sales records"),
    ("reports.read", "View reports"),
    ("reports.export", "Export reports"),
    ("settings.manage", "Manage tenant settings"),
)

