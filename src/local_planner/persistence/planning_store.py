"""Persistence for versioned planning documents. Transactions belong to the UoW."""

import json


class PlanningStore:
    def __init__(self, conn):
        self.conn = conn

    def get(self, draft_id):
        row = self.conn.execute("SELECT payload FROM planning_drafts WHERE id=?", (draft_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self):
        return [json.loads(row[0]) for row in self.conn.execute(
            "SELECT payload FROM planning_drafts ORDER BY updated_at DESC, id DESC")]

    def save(self, draft):
        self.conn.execute(
            "INSERT INTO planning_drafts(id,payload,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
            (draft["id"], json.dumps(draft, ensure_ascii=False), draft["updatedAt"]))

    def delete(self, draft_id):
        self.conn.execute("DELETE FROM planning_requests WHERE draft_id=?", (draft_id,))
        self.conn.execute("DELETE FROM planning_drafts WHERE id=?", (draft_id,))

    def get_request(self, request_id):
        row = self.conn.execute("SELECT fingerprint,draft_id FROM planning_requests WHERE request_id=?",
                                (request_id,)).fetchone()
        return tuple(row) if row else None

    def save_request(self, request_id, fingerprint, draft_id):
        self.conn.execute("INSERT INTO planning_requests VALUES(?,?,?)", (request_id, fingerprint, draft_id))
