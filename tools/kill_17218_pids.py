import os, psycopg2, sys
HOST = os.getenv("PGHOST", "127.0.0.1")
PORT = int(os.getenv("PGPORT", "58529"))
USER = os.getenv("PGUSER", "postgres")
PASSWORD = os.getenv("PGPASSWORD", "postgres")
DB = os.getenv("PGDATABASE", "upbit_trader")

try:
    conn = psycopg2.connect(host=HOST, port=PORT, user=USER, password=PASSWORD, dbname=DB)
    conn.autocommit = True
    cur = conn.cursor()
    # 수집: 종료 대상 PID들
    cur.execute("SELECT pid FROM pg_stat_activity WHERE client_addr = %s AND pid <> pg_backend_pid()", ("172.18.0.1",))
    pids = [r[0] for r in cur.fetchall()]
    print("Terminating PIDs count:", len(pids), "list (first 30):", pids[:30])
    for pid in pids:
        try:
            cur.execute("SELECT pg_terminate_backend(%s)", (pid,))
        except Exception as e:
            print("failed to terminate", pid, e)
    cur.close()
    conn.close()
except Exception as e:
    print("ERROR:", e, file=sys.stderr)
    sys.exit(1)
print("done")
