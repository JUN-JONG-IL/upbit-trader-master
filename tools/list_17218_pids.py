import os, psycopg2, json, sys
HOST = os.getenv("PGHOST", "127.0.0.1")
PORT = int(os.getenv("PGPORT", "58529"))
USER = os.getenv("PGUSER", "postgres")
PASSWORD = os.getenv("PGPASSWORD", "postgres")
DB = os.getenv("PGDATABASE", "upbit_trader")

try:
    conn = psycopg2.connect(host=HOST, port=PORT, user=USER, password=PASSWORD, dbname=DB)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT pid, state, now()-COALESCE(query_start, backend_start) AS duration, left(query,200) FROM pg_stat_activity WHERE client_addr = %s AND pid <> pg_backend_pid() ORDER BY pid", ("172.18.0.1",))
    rows = cur.fetchall()
    cur.close()
    conn.close()
except Exception as e:
    print("ERROR:", e, file=sys.stderr)
    sys.exit(1)

out = {"count": len(rows), "pids": []}
for r in rows:
    out["pids"].append({"pid": r[0], "state": str(r[1]), "duration": str(r[2]), "query_snippet": (r[3] or "")})
print(json.dumps(out, ensure_ascii=False, indent=2))
