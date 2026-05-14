import os, psycopg2, sys
HOST = os.getenv("PGHOST","127.0.0.1")
PORT = int(os.getenv("PGPORT","58529"))
USER = os.getenv("PGUSER","postgres")
PASSWORD = os.getenv("PGPASSWORD","postgres")
DB = os.getenv("PGDATABASE","upbit_trader")

try:
    conn = psycopg2.connect(host=HOST, port=PORT, user=USER, password=PASSWORD, dbname=DB)
    conn.autocommit = True
    cur = conn.cursor()
    # 확인용: 몇 개가 대상인지 먼저 출력
    cur.execute("SELECT count(*) FROM pg_stat_activity WHERE client_addr = %s", ("172.18.0.1",))
    print('matches:', cur.fetchone())
    # 종료 실행: 현재 백엔드(pid) 자신은 제외
    cur.execute(\"\"\"SELECT pid FROM pg_stat_activity WHERE client_addr = %s AND pid <> pg_backend_pid()\"\"\", ("172.18.0.1",))
    pids = [r[0] for r in cur.fetchall()]
    print('will terminate pids (count):', len(pids))
    for pid in pids:
        try:
            cur.execute("SELECT pg_terminate_backend(%s)", (pid,))
        except Exception as e:
            print('terminate failed', pid, e)
    cur.close()
    conn.close()
    print('done')
except Exception as e:
    print('error', e, file=sys.stderr)
    sys.exit(1)
