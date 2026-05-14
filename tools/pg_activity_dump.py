import os, json, sys
try:
    import psycopg2
except Exception:
    print("psycopg2가 필요합니다. pip install psycopg2-binary", file=sys.stderr)
    raise SystemExit(2)

HOST = os.getenv("PGHOST", "127.0.0.1")
PORT = int(os.getenv("PGPORT", "58529"))   # default to timescaledb host port
USER = os.getenv("PGUSER", "postgres")
PASSWORD = os.getenv("PGPASSWORD", "postgres")
DB = os.getenv("PGDATABASE", "upbit_trader")

outfn = r"C:\temp\pg_activity.txt"
q1 = """SELECT coalesce(application_name, '') AS application_name, coalesce(client_addr::text, '') AS client_addr, COUNT(*) AS conn_count, string_agg(pid::text, ',') AS pids FROM pg_stat_activity WHERE datname = current_database() GROUP BY application_name, client_addr ORDER BY conn_count DESC LIMIT 50;"""
q2 = """SELECT pid, usename, application_name, client_addr, state, now() - COALESCE(query_start, backend_start) AS duration, left(query, 500) AS query_snippet FROM pg_stat_activity WHERE datname = current_database() ORDER BY duration DESC LIMIT 50;"""

conn = None
try:
    conn = psycopg2.connect(host=HOST, port=PORT, user=USER, password=PASSWORD, dbname=DB)
    cur = conn.cursor()
    cur.execute(q1)
    rows1 = cur.fetchall()
    cur.execute(q2)
    rows2 = cur.fetchall()
    cur.close()
finally:
    if conn:
        conn.close()

with open(outfn, "w", encoding="utf-8") as f:
    f.write("=== Top clients by connections ===\n")
    for r in rows1:
        f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")
    f.write("\n=== Longest running / held sessions ===\n")
    for r in rows2:
        f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")

print("Wrote:", outfn)
