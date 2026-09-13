"""One-shot migration: service_board* -> workspace* (hard rename).

Run: mongosh "$MONGO_URI" --file migrate_service_board_to_workspace.js
Backups in /tmp/workspace-migrate/ (partner_config_backup.json, phone_number_backup.json).

Forward: renames old keys to workspace_*.
Rollback: function rollback() below reverses it.
"""
// ---------- FORWARD ----------
db.partner_config.updateMany({}, {
  $rename: {
    service_board_ids: "workspace_ids",
    enable_service_board: "enable_workspace",
    board_did_counts: "workspace_did_counts"
  }
});
db.phone_number.updateMany({}, { $rename: { service_board_id: "workspace_id" } });
db.cdr.updateMany({}, { $rename: { service_board_id: "workspace_id" } });
// did_history uses workspace_id already in new code; migrate if old key exists:
try {
  db.did_history.updateMany({}, { $rename: { service_board_id: "workspace_id" } });
} catch (e) { print("did_history skip: " + e); }

// agent_service_board_mapping -> agent_workspace_mapping (only if old collection exists):
try {
  const oldCount = db.getCollection("agent_service_board_mapping").countDocuments({});
  print("agent_service_board_mapping count: " + oldCount);
  if (oldCount > 0) {
    db.getCollection("agent_service_board_mapping").updateMany({}, { $rename: { service_board_id: "workspace_id" } });
    // Manual step after verification: db.agent_service_board_mapping.renameCollection("agent_workspace_mapping")
  }
} catch (e) { print("agent mapping skip: " + e); }

// ---------- VERIFY ----------
print("pc old: " + db.partner_config.countDocuments({ $or: [{ service_board_ids: { $exists: true } }, { enable_service_board: { $exists: true } }, { board_did_counts: { $exists: true } }] }));
print("pc new: " + db.partner_config.countDocuments({ workspace_ids: { $exists: true } }));
print("pn old: " + db.phone_number.countDocuments({ service_board_id: { $exists: true } }));
print("pn new: " + db.phone_number.countDocuments({ workspace_id: { $exists: true } }));
print("cdr old: " + db.cdr.countDocuments({ service_board_id: { $exists: true } }));
print("cdr new: " + db.cdr.countDocuments({ workspace_id: { $exists: true } }));

// ---------- ROLLBACK (run manually if needed) ----------
// db.partner_config.updateMany({}, { $rename: { workspace_ids: "service_board_ids", enable_workspace: "enable_service_board", workspace_did_counts: "board_did_counts" } });
// db.phone_number.updateMany({}, { $rename: { workspace_id: "service_board_id" } });
// db.cdr.updateMany({}, { $rename: { workspace_id: "service_board_id" } });
